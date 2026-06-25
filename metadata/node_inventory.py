"""Per-node block inventory for self-healing and locality queries."""

import logging
import threading
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class NodeInventory:
    """Thread-safe inverse index: node_id -> block_ids."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inventory: Dict[str, List[str]] = {}

    def register_inventory(self, node_id: str, block_ids: List[str]) -> None:
        with self._lock:
            self._inventory[node_id] = sorted(set(block_ids))
            log.debug(
                "inventory registered",
                extra={"node_id": node_id, "block_count": len(block_ids)},
            )

    def update_inventory(self, node_id: str, block_ids: List[str]) -> None:
        self.register_inventory(node_id, block_ids)

    def add_block(self, node_id: str, block_id: str) -> None:
        with self._lock:
            blocks = set(self._inventory.get(node_id, []))
            blocks.add(block_id)
            self._inventory[node_id] = sorted(blocks)

    def remove_block(self, node_id: str, block_id: str) -> None:
        with self._lock:
            blocks = self._inventory.get(node_id)
            if blocks is None:
                return
            updated = [bid for bid in blocks if bid != block_id]
            if updated:
                self._inventory[node_id] = updated
            else:
                del self._inventory[node_id]

    def get_inventory(self, node_id: str) -> List[str]:
        with self._lock:
            blocks = self._inventory.get(node_id)
            return list(blocks) if blocks is not None else []

    def remove_inventory(self, node_id: str) -> bool:
        with self._lock:
            if node_id not in self._inventory:
                return False
            del self._inventory[node_id]
            return True

    def get_all_inventory(self) -> Dict[str, List[str]]:
        with self._lock:
            return {node_id: list(blocks) for node_id, blocks in self._inventory.items()}

    def load_from_snapshot(self, inventory: Dict[str, List[str]]) -> None:
        with self._lock:
            self._inventory = {
                node_id: sorted(set(block_ids))
                for node_id, block_ids in inventory.items()
            }
            log.info(
                "node inventory recovered",
                extra={"node_count": len(self._inventory)},
            )

    def rebuild_from_placements(self, placements: Dict[str, List[str]]) -> None:
        """Rebuild inverse index from block -> nodes map."""
        inventory: Dict[str, List[str]] = {}
        for block_id, nodes in placements.items():
            for node_id in nodes:
                inventory.setdefault(node_id, []).append(block_id)
        with self._lock:
            self._inventory = {
                node_id: sorted(block_ids) for node_id, block_ids in inventory.items()
            }
