"""Helpers for in-process Raft clusters (direct RaftNode, no FastAPI globals)."""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from metadata.membership import MembershipRegistry
from metadata.metadata_store import MetadataStore
from metadata.node_inventory import NodeInventory
from metadata.placement_registry import PlacementRegistry
from metadata.raft.alert_store import AlertStore
from metadata.raft.metrics import RaftMetrics
from metadata.raft.node import RaftNode
from metadata.raft.rpc_client import RaftRpcClient
from metadata.raft.state_machine import RaftStateMachine
from metadata.raft.storage import RaftStorage


class InMemoryRaftCluster:
    """Three-node Raft cluster using direct node instances."""

    def __init__(
        self,
        tmp_path: Path,
        node_ids: Optional[List[str]] = None,
        election_min_ms: int = 80,
        election_max_ms: int = 120,
    ) -> None:
        self.tmp_path = tmp_path
        self.node_ids = node_ids or ["metadata1", "metadata2", "metadata3"]
        self.rpc = RaftRpcClient({})
        self.nodes: Dict[str, RaftNode] = {}
        self.registries: Dict[str, MembershipRegistry] = {}
        peer_urls = {nid: f"http://{nid}:9000" for nid in self.node_ids}

        for node_id in self.node_ids:
            base = tmp_path / node_id
            base.mkdir(parents=True, exist_ok=True)
            storage = RaftStorage(base / "raft.db")
            store = MetadataStore(base / "metadata.db")
            registry = MembershipRegistry()
            placement = PlacementRegistry()
            inventory = NodeInventory()
            alerts = AlertStore()
            sm = RaftStateMachine(registry, placement, inventory, store, alerts)
            node = RaftNode(
                node_id=node_id,
                peer_urls=peer_urls,
                storage=storage,
                state_machine=sm,
                metrics=RaftMetrics(),
                election_min_ms=election_min_ms,
                election_max_ms=election_max_ms,
                snapshot_threshold=8,
                rpc_client=self.rpc,
            )
            self.nodes[node_id] = node
            self.registries[node_id] = registry

        self._wire_rpc()

        for node in self.nodes.values():
            node.start()

    def _wire_rpc(self) -> None:
        def request_vote(peer_id: str, request):
            node = self.nodes.get(peer_id)
            if node is None:
                return None
            return node.handle_request_vote(request)

        def append_entries(peer_id: str, request):
            node = self.nodes.get(peer_id)
            if node is None:
                return None
            return node.handle_append_entries(request)

        self.rpc.request_vote = request_vote  # type: ignore[method-assign]
        self.rpc.append_entries = append_entries  # type: ignore[method-assign]
        self.rpc.set_peer_urls({nid: f"http://{nid}:9000" for nid in self.node_ids})

    def wait_for_leader(self, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for node_id, node in self.nodes.items():
                if node.is_leader():
                    return node_id
            time.sleep(0.05)
        raise TimeoutError("No leader elected")

    def leader(self) -> RaftNode:
        leader_id = self.wait_for_leader()
        return self.nodes[leader_id]

    def partition(self, isolated: List[str]) -> None:
        self.rpc.partition(set(isolated))
        for node_id, node in self.nodes.items():
            if node_id in isolated:
                node.partition_peers({p for p in self.node_ids if p not in isolated})
            else:
                node.partition_peers(set(isolated))

    def heal(self) -> None:
        self.rpc.heal_partition()
        for node in self.nodes.values():
            node.heal_partition()

    def stop_all(self) -> None:
        for node in self.nodes.values():
            node.stop()

    def restart_node(self, node_id: str) -> RaftNode:
        old = self.nodes[node_id]
        old.stop()
        base = self.tmp_path / node_id
        storage = RaftStorage(base / "raft.db")
        store = MetadataStore(base / "metadata.db")
        registry = MembershipRegistry()
        placement = PlacementRegistry()
        inventory = NodeInventory()
        alerts = AlertStore()
        sm = RaftStateMachine(registry, placement, inventory, store, alerts)
        peer_urls = {nid: f"http://{nid}:9000" for nid in self.node_ids}
        node = RaftNode(
            node_id=node_id,
            peer_urls=peer_urls,
            storage=storage,
            state_machine=sm,
            metrics=RaftMetrics(),
            election_min_ms=80,
            election_max_ms=120,
            snapshot_threshold=8,
            rpc_client=self.rpc,
        )
        node.start()
        self.nodes[node_id] = node
        self.registries[node_id] = registry
        return node

    def kill_leader(self) -> str:
        leader_id = self.wait_for_leader()
        node = self.nodes[leader_id]
        node.step_down()
        node.stop()
        return leader_id
