"""Handle node restart — replay hints, reconcile inventory, trigger repairs."""

import logging
from typing import Callable, List, Optional

from cluster.anti_entropy_service import AntiEntropyService
from cluster.node_client import NodeClient, NodeClientError
from cluster.replica_health_scanner import ReplicaHealthScanner

log = logging.getLogger(__name__)


class NodeRecoveryService:

    def __init__(
        self,
        node_id: str,
        list_local_blocks_fn: Callable[[], List[str]],
        replay_hints_fn: Callable[[], int],
        rebuild_inventory_fn: Callable[[str, List[str]], None],
        health_scanner: Optional[ReplicaHealthScanner] = None,
        anti_entropy: Optional[AntiEntropyService] = None,
        node_client: Optional[NodeClient] = None,
        get_node_addresses_fn: Optional[Callable] = None,
    ):
        self._node_id = node_id
        self._list_local_blocks = list_local_blocks_fn
        self._replay_hints = replay_hints_fn
        self._rebuild_inventory = rebuild_inventory_fn
        self._health_scanner = health_scanner
        self._anti_entropy = anti_entropy
        self._node_client = node_client or NodeClient()
        self._get_node_addresses = get_node_addresses_fn

    def recover_node(self) -> dict:
        hints_delivered = self._replay_hints()
        inventory_count = self.rebuild_inventory()
        repairs_triggered = 0
        diverged_repaired = 0

        reconcile_result = self.reconcile_node()

        if self._anti_entropy:
            verify = self._anti_entropy.verify_cluster()
            for block_id in verify.get("diverged_blocks", []):
                result = self._anti_entropy.repair_divergence(block_id)
                if result.get("repaired", 0) > 0:
                    diverged_repaired += result["repaired"]
                    repairs_triggered += 1

        return {
            "node_id": self._node_id,
            "hints_delivered": hints_delivered,
            "inventory_blocks": inventory_count,
            "repairs_triggered": repairs_triggered,
            "diverged_repaired": diverged_repaired,
            "reconcile": reconcile_result,
        }

    def reconcile_node(self) -> dict:
        blocks = self._list_local_blocks()
        self._rebuild_inventory(self._node_id, blocks)

        peer_diffs = []
        if self._get_node_addresses and self._health_scanner:
            addresses = self._get_node_addresses()
            for peer_id in addresses:
                if peer_id == self._node_id:
                    continue
                try:
                    diffs = self._health_scanner.compare_node_merkle_trees(
                        self._node_id, peer_id
                    )
                    if diffs:
                        peer_diffs.append({"peer": peer_id, "diff_blocks": diffs})
                except NodeClientError:
                    continue

        return {
            "node_id": self._node_id,
            "local_blocks": len(blocks),
            "peer_divergence": peer_diffs,
        }

    def rebuild_inventory(self) -> int:
        blocks = self._list_local_blocks()
        self._rebuild_inventory(self._node_id, blocks)
        return len(blocks)
