"""Raft cluster metrics."""

import threading
import time
from typing import Dict, List, Optional


class RaftMetrics:
    """Thread-safe counters and gauges for Raft observability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.raft_current_term = 0
        self.raft_leader_changes = 0
        self.raft_log_entries = 0
        self.raft_commit_index = 0
        self.raft_append_latency_ms: List[float] = []
        self.raft_election_count = 0
        self.raft_replication_lag = 0
        self._election_history: List[dict] = []

    def record_term(self, term: int) -> None:
        with self._lock:
            self.raft_current_term = term

    def record_leader_change(self, leader: Optional[str], term: int, reason: str) -> None:
        with self._lock:
            self.raft_leader_changes += 1
            self._election_history.append(
                {
                    "term": term,
                    "winner": leader,
                    "timestamp": int(time.time() * 1000),
                    "reason": reason,
                }
            )
            if len(self._election_history) > 100:
                self._election_history = self._election_history[-100:]

    def record_election(self) -> None:
        with self._lock:
            self.raft_election_count += 1

    def record_log_length(self, length: int) -> None:
        with self._lock:
            self.raft_log_entries = length

    def record_commit_index(self, index: int) -> None:
        with self._lock:
            self.raft_commit_index = index

    def record_append_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.raft_append_latency_ms.append(latency_ms)
            if len(self.raft_append_latency_ms) > 200:
                self.raft_append_latency_ms = self.raft_append_latency_ms[-200:]

    def record_replication_lag(self, lag: int) -> None:
        with self._lock:
            self.raft_replication_lag = lag

    def get_snapshot(self) -> Dict:
        with self._lock:
            latencies = list(self.raft_append_latency_ms)
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
            return {
                "raft_current_term": self.raft_current_term,
                "raft_leader_changes": self.raft_leader_changes,
                "raft_log_entries": self.raft_log_entries,
                "raft_commit_index": self.raft_commit_index,
                "raft_append_latency_ms": round(avg_latency, 2),
                "raft_election_count": self.raft_election_count,
                "raft_replication_lag": self.raft_replication_lag,
                "election_history": list(self._election_history),
            }
