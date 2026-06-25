"""Authoritative in-memory block placement map."""

import logging
import threading
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class PlacementRegistry:
    """Thread-safe registry mapping block IDs to replica node sets."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocks: Dict[str, List[str]] = {}
        self._versions: Dict[str, int] = {}

    def register_block(
        self,
        block_id: str,
        version: int,
        nodes: List[str],
    ) -> None:
        with self._lock:
            self._blocks[block_id] = list(nodes)
            self._versions[block_id] = version
            log.info(
                "block registered",
                extra={"block_id": block_id, "version": version, "nodes": nodes},
            )

    def get_block_locations(self, block_id: str) -> Optional[List[str]]:
        with self._lock:
            nodes = self._blocks.get(block_id)
            return list(nodes) if nodes is not None else None

    def get_block_version(self, block_id: str) -> Optional[int]:
        with self._lock:
            return self._versions.get(block_id)

    def delete_block(self, block_id: str) -> bool:
        with self._lock:
            if block_id not in self._blocks:
                return False
            del self._blocks[block_id]
            self._versions.pop(block_id, None)
            log.info("block deleted", extra={"block_id": block_id})
            return True

    def get_node_blocks(self, node_id: str) -> List[str]:
        with self._lock:
            return sorted(
                block_id
                for block_id, nodes in self._blocks.items()
                if node_id in nodes
            )

    def block_exists(self, block_id: str) -> bool:
        with self._lock:
            return block_id in self._blocks

    def list_all_blocks(self) -> Dict[str, List[str]]:
        with self._lock:
            return {block_id: list(nodes) for block_id, nodes in self._blocks.items()}

    def load_from_snapshot(
        self,
        blocks: Dict[str, List[str]],
        versions: Optional[Dict[str, int]] = None,
    ) -> None:
        """Replace registry state from a persisted snapshot (startup recovery)."""
        with self._lock:
            self._blocks = {block_id: list(nodes) for block_id, nodes in blocks.items()}
            self._versions = dict(versions or {})
            log.info("placement registry recovered", extra={"block_count": len(self._blocks)})
