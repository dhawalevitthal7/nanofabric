"""Raft node — leader election, log replication, and commit."""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from metadata.raft.election import (
    is_log_up_to_date,
    majority_count,
    random_election_timeout_ms,
)
from metadata.raft.metrics import RaftMetrics
from metadata.raft.models import (
    AppendEntriesRequest,
    AppendEntriesResponse,
    CommandType,
    LogEntry,
    ProposeResult,
    RaftRole,
    RequestVoteRequest,
    RequestVoteResponse,
)
from metadata.raft.rpc_client import RaftRpcClient
from metadata.raft.snapshot import SnapshotManager
from metadata.raft.state_machine import RaftStateMachine
from metadata.raft.storage import RaftStorage

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SEC = 0.05


class RaftNode:
    """Single Raft peer for the metadata control plane."""

    def __init__(
        self,
        node_id: str,
        peer_urls: Dict[str, str],
        storage: RaftStorage,
        state_machine: RaftStateMachine,
        metrics: Optional[RaftMetrics] = None,
        election_min_ms: int = 150,
        election_max_ms: int = 300,
        snapshot_threshold: int = 50,
        rpc_client: Optional[RaftRpcClient] = None,
    ) -> None:
        self.node_id = node_id
        self.peer_urls = dict(peer_urls)
        self._storage = storage
        self._state_machine = state_machine
        self._metrics = metrics or RaftMetrics()
        self._election_min_ms = election_min_ms
        self._election_max_ms = election_max_ms

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        term, voted_for = storage.get_state()
        self.current_term = term
        self.voted_for = voted_for
        self.role = RaftRole.FOLLOWER
        self.leader_id: Optional[str] = None

        self.log: List[LogEntry] = storage.get_log()
        self.commit_index = 0
        self.last_applied = 0
        self.snapshot_index = 0
        self.snapshot_term = 0

        self._next_index: Dict[str, int] = {}
        self._match_index: Dict[str, int] = {}
        self._votes_received = 0

        self._election_deadline = time.monotonic() + random_election_timeout_ms(
            election_min_ms, election_max_ms
        )

        self._rpc = rpc_client or RaftRpcClient(self.peer_urls)
        self._snapshot_mgr = SnapshotManager(storage, state_machine, snapshot_threshold)

        self._metrics.record_term(self.current_term)
        self._metrics.record_log_length(len(self.log))

    @property
    def peers(self) -> List[str]:
        return [p for p in self.peer_urls if p != self.node_id]

    def start(self) -> None:
        restored = self._snapshot_mgr.restore(self)
        with self._lock:
            if restored > 0:
                self.commit_index = restored
                self.last_applied = restored
            self._apply_pending_commits()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"raft-{self.node_id}")
        self._thread.start()
        log.info("raft node started", extra={"node_id": self.node_id, "peers": self.peers})

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def is_leader(self) -> bool:
        alive = self._thread is not None and self._thread.is_alive()
        return self.role == RaftRole.LEADER and alive

    def leader_url(self) -> Optional[str]:
        if self.leader_id is None:
            return None
        return self.peer_urls.get(self.leader_id) or (
            self.peer_urls.get(self.node_id) if self.leader_id == self.node_id else None
        )

    def get_status(self) -> dict:
        with self._lock:
            lag = max(0, len(self.log) - self.commit_index)
            self._metrics.record_replication_lag(lag)
            return {
                "node_id": self.node_id,
                "leader": self.leader_id,
                "term": self.current_term,
                "role": self.role.value,
                "commit_index": self.commit_index,
                "last_applied": self.last_applied,
                "log_length": len(self.log),
                "peers": self.peers,
                "replication_lag": lag,
            }

    def log_term_at(self, index: int) -> int:
        if index <= 0:
            return self.snapshot_term
        if index <= len(self.log):
            return self.log[index - 1].term
        return 0

    def last_log_info(self) -> Tuple[int, int]:
        if not self.log:
            return self.snapshot_index, self.snapshot_term
        entry = self.log[-1]
        return entry.index, entry.term

    def on_snapshot_created(self, last_index: int) -> None:
        with self._lock:
            self.snapshot_index = last_index
            self.snapshot_term = self.log_term_at(last_index)
            self.log = [e for e in self.log if e.index > last_index]

    def on_snapshot_restored(self, last_index: int, last_term: int) -> None:
        with self._lock:
            self.snapshot_index = last_index
            self.snapshot_term = last_term
            self.log = [e for e in self.log if e.index > last_index]

    def propose(self, command: CommandType, payload: dict, timeout: float = 2.0) -> ProposeResult:
        if not self.is_leader():
            return ProposeResult(success=False, error="not leader")

        deadline = time.monotonic() + timeout
        with self._lock:
            entry = self._append_local_entry(command, payload)
            start_index = entry.index
            peers = list(self.peers)
            if not peers:
                self._advance_commit_index()

        for peer in peers:
            self._replicate_to_peer(peer)

        while time.monotonic() < deadline:
            with self._lock:
                if self.commit_index >= start_index:
                    return ProposeResult(success=True, index=start_index)
                if self.role != RaftRole.LEADER:
                    return ProposeResult(success=False, error="lost leadership")
            for peer in peers:
                self._replicate_to_peer(peer)
            time.sleep(0.01)

        return ProposeResult(success=False, error="commit timeout")

    def handle_request_vote(self, req: RequestVoteRequest) -> RequestVoteResponse:
        with self._lock:
            if req.term < self.current_term:
                return RequestVoteResponse(term=self.current_term, vote_granted=False)

            if req.term > self.current_term:
                self._become_follower(req.term)

            last_idx, last_term = self.last_log_info()
            up_to_date = is_log_up_to_date(
                req.last_log_index, req.last_log_term, last_idx, last_term
            )

            if (
                (self.voted_for is None or self.voted_for == req.candidate_id)
                and up_to_date
            ):
                self.voted_for = req.candidate_id
                self._persist_state()
                self._reset_election_timer()
                log.info(
                    "vote granted",
                    extra={"candidate": req.candidate_id, "term": req.term},
                )
                return RequestVoteResponse(term=self.current_term, vote_granted=True)

            return RequestVoteResponse(term=self.current_term, vote_granted=False)

    def handle_append_entries(self, req: AppendEntriesRequest) -> AppendEntriesResponse:
        with self._lock:
            if req.term < self.current_term:
                return AppendEntriesResponse(term=self.current_term, success=False)

            self._become_follower(req.term, req.leader_id)
            self._reset_election_timer()

            if req.prev_log_index > 0:
                if req.prev_log_index > len(self.log):
                    return AppendEntriesResponse(term=self.current_term, success=False)
                if self.log[req.prev_log_index - 1].term != req.prev_log_term:
                    return AppendEntriesResponse(term=self.current_term, success=False)

            if req.entries:
                for entry in req.entries:
                    idx = entry.index
                    if idx <= len(self.log):
                        if self.log[idx - 1].term != entry.term:
                            self.log = self.log[: idx - 1]
                            self._storage.truncate_log_from(idx)
                    if idx > len(self.log):
                        self.log.append(entry)
                self._storage.append_entries(req.entries)
                self._metrics.record_log_length(len(self.log))

            if req.leader_commit > self.commit_index:
                self.commit_index = min(req.leader_commit, len(self.log))
                self._apply_pending_commits()

            match = req.prev_log_index + len(req.entries)
            return AppendEntriesResponse(
                term=self.current_term, success=True, match_index=match
            )

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                is_leader = self.role == RaftRole.LEADER
                should_elect = (
                    self.role != RaftRole.LEADER
                    and time.monotonic() >= self._election_deadline
                )
            if is_leader:
                self._send_heartbeats()
            elif should_elect:
                self._start_election()
            time.sleep(HEARTBEAT_INTERVAL_SEC)

    def _start_election(self) -> None:
        with self._lock:
            if self.role == RaftRole.LEADER:
                return
            self.role = RaftRole.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self.leader_id = None
            self._votes_received = 1
            self._persist_state()
            self._metrics.record_term(self.current_term)
            self._metrics.record_election()
            self._reset_election_timer()
            last_idx, last_term = self.last_log_info()
            term = self.current_term
            node_id = self.node_id
            peers = list(self.peers)

        log.info("election started", extra={"term": term, "node": node_id})

        for peer in peers:
            req = RequestVoteRequest(
                term=term,
                candidate_id=node_id,
                last_log_index=last_idx,
                last_log_term=last_term,
            )
            resp = self._rpc.request_vote(peer, req)
            with self._lock:
                if resp is None:
                    continue
                if resp.term > self.current_term:
                    self._become_follower(resp.term)
                    return
                if resp.vote_granted:
                    self._votes_received += 1

        with self._lock:
            if (
                self.role == RaftRole.CANDIDATE
                and self._votes_received >= majority_count(len(self.peers))
            ):
                self._become_leader()

    def _become_leader(self) -> None:
        self.role = RaftRole.LEADER
        self.leader_id = self.node_id
        last_idx, _ = self.last_log_info()
        for peer in self.peers:
            self._next_index[peer] = last_idx + 1
            self._match_index[peer] = 0
        self._metrics.record_leader_change(self.node_id, self.current_term, "election_won")
        log.info("became leader", extra={"node": self.node_id, "term": self.current_term})
        self._send_heartbeats()

    def _become_follower(self, term: int, leader_id: Optional[str] = None) -> None:
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self._metrics.record_term(self.current_term)
        self.role = RaftRole.FOLLOWER
        if leader_id:
            if self.leader_id != leader_id:
                self._metrics.record_leader_change(leader_id, self.current_term, "discovered_leader")
            self.leader_id = leader_id
        self._persist_state()
        self._reset_election_timer()

    def _send_heartbeats(self) -> None:
        for peer in self.peers:
            self._replicate_to_peer(peer)

    def _replicate_to_peer(self, peer: str) -> None:
        with self._lock:
            if self.role != RaftRole.LEADER:
                return
            next_idx = self._next_index.get(peer, 1)
            prev_index = next_idx - 1
            prev_term = self.log_term_at(prev_index)
            entries = [e for e in self.log if e.index >= next_idx]
            req = AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_index,
                prev_log_term=prev_term,
                entries=entries,
                leader_commit=self.commit_index,
            )

        start = time.monotonic()
        resp = self._rpc.append_entries(peer, req)
        latency = (time.monotonic() - start) * 1000
        self._metrics.record_append_latency(latency)

        if resp is None:
            return

        with self._lock:
            if resp.term > self.current_term:
                self._become_follower(resp.term)
                return

            if resp.success:
                if entries:
                    self._match_index[peer] = entries[-1].index
                    self._next_index[peer] = entries[-1].index + 1
                else:
                    self._match_index[peer] = prev_index
                self._advance_commit_index()
            else:
                if next_idx > 1:
                    self._next_index[peer] = next_idx - 1

    def _advance_commit_index(self) -> None:
        for n in range(len(self.log), self.commit_index, -1):
            if self.log[n - 1].term != self.current_term:
                continue
            count = 1
            for peer in self.peers:
                if self._match_index.get(peer, 0) >= n:
                    count += 1
            if count >= majority_count(len(self.peers)):
                self.commit_index = n
                self._apply_pending_commits()
                self._snapshot_mgr.maybe_snapshot(self)
                break

    def _append_local_entry(self, command: CommandType, payload: dict) -> LogEntry:
        if self.log:
            index = self.log[-1].index + 1
        else:
            index = self.snapshot_index + 1

        entry = LogEntry(index=index, term=self.current_term, command=command, payload=payload)
        self.log.append(entry)
        self._storage.append_entries([entry])
        self._metrics.record_log_length(len(self.log))
        self._metrics.record_commit_index(self.commit_index)
        return entry

    def _apply_pending_commits(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            if self.last_applied <= len(self.log):
                entry = self.log[self.last_applied - 1]
                self._state_machine.apply(entry)
        self._metrics.record_commit_index(self.commit_index)

    def _persist_state(self) -> None:
        self._storage.set_state(self.current_term, self.voted_for)

    def _reset_election_timer(self) -> None:
        self._election_deadline = time.monotonic() + random_election_timeout_ms(
            self._election_min_ms, self._election_max_ms
        )

    def reconfigure_peers(self, peer_urls: Dict[str, str]) -> None:
        with self._lock:
            self.peer_urls = dict(peer_urls)
            self._rpc.set_peer_urls(self.peer_urls)

    def partition_peers(self, peer_ids: set) -> None:
        self._rpc.partition(peer_ids)

    def heal_partition(self) -> None:
        self._rpc.heal_partition()

    def step_down(self) -> None:
        """Force node to follower (for testing leader crash)."""
        with self._lock:
            self.role = RaftRole.FOLLOWER
            self.leader_id = None
            self._reset_election_timer()
