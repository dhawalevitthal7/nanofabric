"""Continuous cluster health inspection for replica imbalances and divergence."""

import logging
from typing import Callable, Dict, List, Optional, Set

from cluster.node_client import NodeClient, NodeClientError
from cluster.repair_models import (
    ClusterHealthReport,
    DivergedBlock,
    OrphanBlock,
    OverReplicatedBlock,
    UnderReplicatedBlock,
)
from node.merkle import MerkleTree, compare_trees

log = logging.getLogger(__name__)


class ReplicaHealthScanner:

    def __init__(
        self,
        list_placements_fn: Callable[[], Dict[str, List[str]]],
        get_block_version_fn: Callable[[str], Optional[int]],
        get_healthy_nodes_fn: Callable[[], List[str]],
        get_node_addresses_fn: Callable[[], Dict[str, str]],
        node_client: Optional[NodeClient] = None,
        get_metadata_inventory_fn: Optional[Callable[[str], List[str]]] = None,
    ):
        self._list_placements = list_placements_fn
        self._get_block_version = get_block_version_fn
        self._get_healthy_nodes = get_healthy_nodes_fn
        self._get_node_addresses = get_node_addresses_fn
        self._node_client = node_client or NodeClient()
        self._get_metadata_inventory = get_metadata_inventory_fn

    def scan_cluster(self) -> ClusterHealthReport:
        return ClusterHealthReport(
            under_replicated=self.find_under_replicated(),
            over_replicated=self.find_over_replicated(),
            diverged=self.find_diverged(),
            orphans=self.find_orphans(),
        )

    def find_under_replicated(self) -> List[UnderReplicatedBlock]:
        placements = self._list_placements()
        healthy = set(self._get_healthy_nodes())
        addresses = self._get_node_addresses()
        results: List[UnderReplicatedBlock] = []

        for block_id, desired_nodes in placements.items():
            version = self._get_block_version(block_id) or 1
            reachable_desired = [n for n in desired_nodes if n in healthy]
            present = []
            missing = []
            for node_id in desired_nodes:
                if node_id not in healthy:
                    missing.append(node_id)
                    continue
                try:
                    if self._node_client.has_block(node_id, block_id, addresses):
                        present.append(node_id)
                    else:
                        missing.append(node_id)
                except NodeClientError:
                    missing.append(node_id)

            if len(present) < len(reachable_desired) or missing:
                results.append(
                    UnderReplicatedBlock(
                        block_id=block_id,
                        version=version,
                        desired_nodes=list(desired_nodes),
                        present_nodes=present,
                        missing_nodes=missing,
                    )
                )
        return results

    def find_over_replicated(self) -> List[OverReplicatedBlock]:
        placements = self._list_placements()
        addresses = self._get_node_addresses()
        healthy = set(self._get_healthy_nodes())
        results: List[OverReplicatedBlock] = []

        for block_id, desired_nodes in placements.items():
            version = self._get_block_version(block_id) or 1
            desired_set = set(desired_nodes)
            extra_nodes: List[str] = []

            for node_id in healthy:
                if node_id in desired_set:
                    continue
                try:
                    if self._node_client.has_block(node_id, block_id, addresses):
                        extra_nodes.append(node_id)
                except NodeClientError:
                    continue

            if extra_nodes:
                results.append(
                    OverReplicatedBlock(
                        block_id=block_id,
                        version=version,
                        desired_nodes=list(desired_nodes),
                        extra_nodes=extra_nodes,
                    )
                )
        return results

    def find_diverged(self) -> List[DivergedBlock]:
        placements = self._list_placements()
        addresses = self._get_node_addresses()
        healthy = set(self._get_healthy_nodes())
        results: List[DivergedBlock] = []

        for block_id, desired_nodes in placements.items():
            node_hashes: Dict[str, str] = {}
            for node_id in desired_nodes:
                if node_id not in healthy:
                    continue
                try:
                    record = self._node_client.read_block(node_id, block_id, addresses)
                    if record is None or record.get("deleted"):
                        continue
                    leaf_hash = MerkleTree(
                        {block_id: (record["data"], record["version"])}
                    ).leaf_hashes().get(block_id, "")
                    node_hashes[node_id] = leaf_hash
                except NodeClientError:
                    continue

            unique_hashes = set(node_hashes.values())
            if len(unique_hashes) > 1:
                results.append(DivergedBlock(block_id=block_id, node_hashes=node_hashes))

        return results

    def find_orphans(self) -> List[OrphanBlock]:
        placements = self._list_placements()
        placement_blocks: Set[str] = set(placements.keys())
        addresses = self._get_node_addresses()
        healthy = self._get_healthy_nodes()
        results: List[OrphanBlock] = []

        node_blocks: Dict[str, Set[str]] = {}
        for node_id in healthy:
            try:
                blocks = self._node_client.list_blocks(node_id, addresses)
                node_blocks[node_id] = set(blocks)
            except NodeClientError:
                continue

        for block_id, nodes in placements.items():
            for node_id in nodes:
                if node_id not in node_blocks:
                    continue
                if block_id not in node_blocks[node_id]:
                    results.append(
                        OrphanBlock(
                            block_id=block_id,
                            orphan_type="metadata_only",
                            node_id=node_id,
                        )
                    )

        all_node_block_ids: Set[str] = set()
        for blocks in node_blocks.values():
            all_node_block_ids |= blocks

        for block_id in all_node_block_ids - placement_blocks:
            for node_id, blocks in node_blocks.items():
                if block_id in blocks:
                    results.append(
                        OrphanBlock(
                            block_id=block_id,
                            orphan_type="block_only",
                            node_id=node_id,
                        )
                    )
                    break

        if self._get_metadata_inventory:
            for node_id in healthy:
                meta_blocks = set(self._get_metadata_inventory(node_id))
                actual_blocks = node_blocks.get(node_id, set())
                for block_id in meta_blocks - actual_blocks:
                    if block_id in placement_blocks:
                        results.append(
                            OrphanBlock(
                                block_id=block_id,
                                orphan_type="metadata_only",
                                node_id=node_id,
                            )
                        )
                for block_id in actual_blocks - meta_blocks:
                    if block_id not in placement_blocks:
                        results.append(
                            OrphanBlock(
                                block_id=block_id,
                                orphan_type="block_only",
                                node_id=node_id,
                            )
                        )

        return results

    def compare_node_merkle_trees(
        self,
        node_a: str,
        node_b: str,
    ) -> List[str]:
        addresses = self._get_node_addresses()
        blocks_a = self._load_node_blocks(node_a, addresses)
        blocks_b = self._load_node_blocks(node_b, addresses)
        tree_a = MerkleTree(blocks_a)
        tree_b = MerkleTree(blocks_b)
        return compare_trees(tree_a, tree_b)

    def _load_node_blocks(
        self,
        node_id: str,
        addresses: Dict[str, str],
    ) -> Dict[str, tuple]:
        blocks: Dict[str, tuple] = {}
        for block_id in self._node_client.list_blocks(node_id, addresses):
            record = self._node_client.read_block(node_id, block_id, addresses)
            if record and not record.get("deleted"):
                blocks[block_id] = (record["data"], record["version"])
        return blocks
