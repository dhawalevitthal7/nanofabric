"""Orchestrates placement policy, registry, inventory, and durable store."""

import logging
from typing import Dict, List, Optional

from metadata.membership import MembershipRegistry
from metadata.metadata_store import MetadataStore
from metadata.models import NodeStatus
from metadata.node_inventory import NodeInventory
from metadata.placement_policy import PlacementPolicy
from metadata.placement_registry import PlacementRegistry

log = logging.getLogger(__name__)


class BlockAlreadyExistsError(Exception):
    """Raised when allocating a block that already has a placement."""


class InsufficientNodesError(Exception):
    """Raised when not enough healthy nodes exist for the requested RF."""


class PlacementService:
    """Coordinates block allocation and placement lookups."""

    def __init__(
        self,
        registry: MembershipRegistry,
        placement_registry: PlacementRegistry,
        inventory: NodeInventory,
        store: MetadataStore,
        policy: PlacementPolicy,
    ) -> None:
        self._membership = registry
        self._placement_registry = placement_registry
        self._inventory = inventory
        self._store = store
        self._policy = policy

    def get_healthy_nodes(self) -> List[str]:
        summary = self._membership.get_cluster_summary()
        return sorted(
            node_id for node_id, status in summary.items() if status == NodeStatus.UP.value
        )

    def allocate_block(self, block_id: str, rf: int = 1, version: int = 1) -> List[str]:
        if self._placement_registry.block_exists(block_id):
            raise BlockAlreadyExistsError(f"Block '{block_id}' already allocated")

        healthy = self.get_healthy_nodes()
        if len(healthy) < rf:
            raise InsufficientNodesError(
                f"Need {rf} healthy nodes but only {len(healthy)} available"
            )

        nodes = self._policy.select_nodes(healthy, rf)
        self._store.save_placement(block_id, version, nodes)
        self._placement_registry.register_block(block_id, version, nodes)
        for node_id in nodes:
            self._inventory.add_block(node_id, block_id)

        log.info(
            "block allocated",
            extra={"block_id": block_id, "rf": rf, "nodes": nodes},
        )
        return nodes

    def get_block_locations(self, block_id: str) -> Optional[List[str]]:
        return self._placement_registry.get_block_locations(block_id)

    def delete_block(self, block_id: str) -> bool:
        locations = self._placement_registry.get_block_locations(block_id)
        if locations is None:
            return False

        deleted = self._store.delete_block(block_id)
        if not deleted:
            return False

        self._placement_registry.delete_block(block_id)
        for node_id in locations:
            self._inventory.remove_block(node_id, block_id)
        return True

    def list_all_placements(self) -> Dict[str, List[str]]:
        return self._placement_registry.list_all_blocks()

    def get_node_blocks(self, node_id: str) -> List[str]:
        return self._inventory.get_inventory(node_id)

    def get_metadata_stats(self) -> Dict[str, int]:
        return self._store.get_stats()

    def update_block_placement(
        self,
        block_id: str,
        nodes: List[str],
        version: int,
    ) -> List[str]:
        if not self._placement_registry.block_exists(block_id):
            raise KeyError(f"Block '{block_id}' not found")

        old_locations = self._placement_registry.get_block_locations(block_id) or []
        self._store.save_placement(block_id, version, nodes)
        self._placement_registry.register_block(block_id, version, nodes)
        for node_id in old_locations:
            if node_id not in nodes:
                self._inventory.remove_block(node_id, block_id)
        for node_id in nodes:
            if node_id not in old_locations:
                self._inventory.add_block(node_id, block_id)
        return nodes

    def replace_replica(
        self,
        block_id: str,
        old_node: str,
        new_node: str,
        version: int,
    ) -> List[str]:
        locations = self._placement_registry.get_block_locations(block_id)
        if locations is None:
            raise KeyError(f"Block '{block_id}' not found")

        new_locations = [new_node if n == old_node else n for n in locations]
        if old_node not in locations and new_node not in locations:
            new_locations = list(locations) + [new_node]
        return self.update_block_placement(block_id, new_locations, version)

    def remove_extra_replica(
        self,
        block_id: str,
        extra_node: str,
        version: int,
    ) -> List[str]:
        locations = self._placement_registry.get_block_locations(block_id)
        if locations is None:
            raise KeyError(f"Block '{block_id}' not found")

        new_locations = [n for n in locations if n != extra_node]
        if len(new_locations) == len(locations):
            return locations
        return self.update_block_placement(block_id, new_locations, version)

    def rebuild_node_inventory(self, node_id: str, block_ids: List[str]) -> None:
        self._inventory.register_inventory(node_id, block_ids)

    def get_block_version(self, block_id: str) -> Optional[int]:
        return self._placement_registry.get_block_version(block_id)

    def recover(self) -> None:
        """Load persisted placements and rebuild in-memory structures."""
        placements, versions, block_count = self._store.load_recovery_snapshot()
        self._placement_registry.load_from_snapshot(placements, versions)
        self._inventory.rebuild_from_placements(placements)
        if hasattr(self._policy, "advance"):
            self._policy.advance(block_count)
        log.info("placement service recovered", extra={"block_count": block_count})
