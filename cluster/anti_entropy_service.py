"""Merkle-tree based anti-entropy for replica consistency."""

import logging
from typing import Callable, Dict, List, Optional

from cluster.node_client import NodeClient, NodeClientError
from cluster.re_replication_service import ReReplicationService
from cluster.repair_models import DivergedBlock, RepairType
from node.merkle import MerkleTree, compare_trees, trees_match

log = logging.getLogger(__name__)


class AntiEntropyService:

    def __init__(
        self,
        list_placements_fn: Callable[[], Dict[str, List[str]]],
        get_healthy_nodes_fn: Callable[[], List[str]],
        get_node_addresses_fn: Callable[[], Dict[str, str]],
        re_replication: ReReplicationService,
        node_client: Optional[NodeClient] = None,
        metrics=None,
    ):
        self._list_placements = list_placements_fn
        self._get_healthy_nodes = get_healthy_nodes_fn
        self._get_node_addresses = get_node_addresses_fn
        self._re_replication = re_replication
        self._node_client = node_client or NodeClient()
        self._metrics = metrics

    def compare_replicas(self, block_id: str) -> Optional[DivergedBlock]:
        placements = self._list_placements()
        nodes = placements.get(block_id, [])
        addresses = self._get_node_addresses()
        node_hashes: Dict[str, str] = {}

        for node_id in nodes:
            try:
                record = self._node_client.read_block(node_id, block_id, addresses)
                if record is None or record.get("deleted"):
                    continue
                leaf = MerkleTree(
                    {block_id: (record["data"], record["version"])}
                ).leaf_hashes().get(block_id, "")
                node_hashes[node_id] = leaf
            except NodeClientError:
                continue

        if len(set(node_hashes.values())) > 1:
            return DivergedBlock(block_id=block_id, node_hashes=node_hashes)
        return None

    def repair_divergence(self, block_id: str) -> dict:
        diverged = self.compare_replicas(block_id)
        if diverged is None:
            return {"ok": True, "repaired": 0, "block_id": block_id}

        addresses = self._get_node_addresses()
        latest_node, latest_record = self._find_latest(block_id, diverged.node_hashes.keys(), addresses)
        if latest_node is None or latest_record is None:
            return {"ok": False, "error": "no authoritative copy found"}

        repaired = 0
        version = latest_record.get("version", 1)
        for node_id in diverged.node_hashes:
            if node_id == latest_node:
                continue
            result = self._re_replication.repair_block(
                block_id=block_id,
                version=version,
                source_node=latest_node,
                target_node=node_id,
                repair_type=RepairType.ANTI_ENTROPY,
            )
            if result.get("ok"):
                repaired += 1
                if self._metrics:
                    self._metrics.inc_anti_entropy_repairs()

        return {"ok": True, "repaired": repaired, "block_id": block_id, "source": latest_node}

    def verify_cluster(self) -> dict:
        healthy = self._get_healthy_nodes()
        addresses = self._get_node_addresses()
        diverged_blocks: List[str] = []

        if len(healthy) >= 2:
            reference = healthy[0]
            ref_blocks = self._load_blocks(reference, addresses)
            ref_tree = MerkleTree(ref_blocks)
            for node_id in healthy[1:]:
                node_blocks = self._load_blocks(node_id, addresses)
                node_tree = MerkleTree(node_blocks)
                if not trees_match(ref_tree, node_tree):
                    diverged_blocks.extend(compare_trees(ref_tree, node_tree))

        per_block = []
        placements = self._list_placements()
        for block_id in placements:
            d = self.compare_replicas(block_id)
            if d:
                per_block.append(block_id)

        all_diverged = sorted(set(diverged_blocks) | set(per_block))
        return {
            "healthy": len(all_diverged) == 0,
            "diverged_blocks": all_diverged,
            "diverged_count": len(all_diverged),
        }

    def _find_latest(
        self,
        block_id: str,
        nodes,
        addresses: Dict[str, str],
    ):
        from node.version_reconciliation import ReplicaCopy, select_latest

        copies: List[ReplicaCopy] = []
        for node_id in nodes:
            try:
                record = self._node_client.read_block(node_id, block_id, addresses)
                if record and not record.get("deleted"):
                    copies.append(
                        ReplicaCopy(
                            node_id=node_id,
                            block_id=block_id,
                            data=record["data"],
                            version=record["version"],
                            lsn=record.get("origin_lsn", 0),
                        )
                    )
            except NodeClientError:
                continue
        latest = select_latest(copies)
        if latest is None:
            return None, None
        return latest.node_id, {
            "data": latest.data,
            "version": latest.version,
            "origin_lsn": latest.lsn,
        }

    def _load_blocks(self, node_id: str, addresses: Dict[str, str]) -> Dict[str, tuple]:
        blocks: Dict[str, tuple] = {}
        try:
            for block_id in self._node_client.list_blocks(node_id, addresses):
                record = self._node_client.read_block(node_id, block_id, addresses)
                if record and not record.get("deleted"):
                    blocks[block_id] = (record["data"], record["version"])
        except NodeClientError:
            pass
        return blocks
