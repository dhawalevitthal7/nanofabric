"""Ensure metadata placements match on-disk node reality."""

import logging
from typing import Callable, Dict, List, Optional, Set

from cluster.node_client import NodeClient, NodeClientError
from cluster.repair_models import OrphanBlock

log = logging.getLogger(__name__)


class PlacementReconciliation:

    def __init__(
        self,
        list_placements_fn: Callable[[], Dict[str, List[str]]],
        get_node_inventory_fn: Callable[[str], List[str]],
        update_placement_fn: Callable[[str, List[str], int], List[str]],
        rebuild_inventory_fn: Callable[[str, List[str]], None],
        get_node_addresses_fn: Callable[[], Dict[str, str]],
        get_block_version_fn: Callable[[str], Optional[int]],
        node_client: Optional[NodeClient] = None,
    ):
        self._list_placements = list_placements_fn
        self._get_node_inventory = get_node_inventory_fn
        self._update_placement = update_placement_fn
        self._rebuild_inventory = rebuild_inventory_fn
        self._get_node_addresses = get_node_addresses_fn
        self._get_block_version = get_block_version_fn
        self._node_client = node_client or NodeClient()

    def detect_mismatches(self) -> Dict[str, List[OrphanBlock]]:
        placements = self._list_placements()
        addresses = self._get_node_addresses()
        metadata_only: List[OrphanBlock] = []
        block_only: List[OrphanBlock] = []

        for block_id, nodes in placements.items():
            for node_id in nodes:
                inventory = set(self._get_node_inventory(node_id))
                if block_id not in inventory:
                    metadata_only.append(
                        OrphanBlock(
                            block_id=block_id,
                            orphan_type="metadata_only",
                            node_id=node_id,
                        )
                    )
                try:
                    if not self._node_client.has_block(node_id, block_id, addresses):
                        if not any(
                            o.block_id == block_id and o.node_id == node_id
                            for o in metadata_only
                        ):
                            metadata_only.append(
                                OrphanBlock(
                                    block_id=block_id,
                                    orphan_type="metadata_only",
                                    node_id=node_id,
                                )
                            )
                except NodeClientError:
                    pass

        placement_blocks: Set[str] = set(placements.keys())
        for node_id, inventory_blocks in self._scan_node_inventories(addresses).items():
            for block_id in inventory_blocks:
                if block_id not in placement_blocks:
                    block_only.append(
                        OrphanBlock(
                            block_id=block_id,
                            orphan_type="block_only",
                            node_id=node_id,
                        )
                    )

        return {"metadata_only": metadata_only, "block_only": block_only}

    def reconcile(self) -> dict:
        mismatches = self.detect_mismatches()
        rebuilt_metadata = 0
        cleaned_orphans = 0
        addresses = self._get_node_addresses()

        for orphan in mismatches["metadata_only"]:
            block_id = orphan.block_id
            node_id = orphan.node_id
            if not node_id:
                continue
            source = self._find_source_node(block_id, addresses)
            if source:
                version = self._get_block_version(block_id) or 1
                placements = self._list_placements()
                nodes = list(placements.get(block_id, []))
                if node_id not in nodes:
                    nodes.append(node_id)
                self._update_placement(block_id, nodes, version)
                rebuilt_metadata += 1

        for orphan in mismatches["block_only"]:
            node_id = orphan.node_id
            if node_id:
                blocks = self._node_client.list_blocks(node_id, addresses)
                self._rebuild_inventory(node_id, blocks)
                cleaned_orphans += 1

        return {
            "rebuilt_metadata": rebuilt_metadata,
            "cleaned_orphans": cleaned_orphans,
            "metadata_only": len(mismatches["metadata_only"]),
            "block_only": len(mismatches["block_only"]),
        }

    def rebuild_metadata_from_node(self, node_id: str) -> int:
        addresses = self._get_node_addresses()
        blocks = self._node_client.list_blocks(node_id, addresses)
        self._rebuild_inventory(node_id, blocks)
        return len(blocks)

    def _scan_node_inventories(
        self,
        addresses: Dict[str, str],
    ) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for node_id in addresses:
            try:
                result[node_id] = set(self._node_client.list_blocks(node_id, addresses))
            except NodeClientError:
                result[node_id] = set()
        return result

    def _find_source_node(
        self,
        block_id: str,
        addresses: Dict[str, str],
    ) -> Optional[str]:
        placements = self._list_placements()
        for node_id in placements.get(block_id, []):
            try:
                if self._node_client.has_block(node_id, block_id, addresses):
                    return node_id
            except NodeClientError:
                continue
        for node_id in addresses:
            try:
                if self._node_client.has_block(node_id, block_id, addresses):
                    return node_id
            except NodeClientError:
                continue
        return None
