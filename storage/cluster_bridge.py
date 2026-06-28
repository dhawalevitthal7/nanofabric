"""Bridge between protection services and cluster nodes."""

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

import httpx

from node.storage_engine import BlockRecord, StorageEngine

log = logging.getLogger(__name__)


@dataclass
class _BlockView:
    block_id: str
    data: str
    version: int
    deleted: bool = False


class EngineBlockAdapter:
    """Read/write adapter backed by a local StorageEngine (tests and single-node)."""

    def __init__(self, engine: StorageEngine):
        self._engine = engine

    def list_blocks(self) -> List[str]:
        return self._engine.list_blocks()

    def read_block(self, block_id: str) -> Optional[BlockRecord]:
        return self._engine.read_block(block_id)

    def write_local(self, block_id: str, data: str, version: int):
        return self._engine.write_local(
            block_id, data, version, allow_idempotent=True
        )

    def delete_local(self, block_id: str, version: int):
        return self._engine.delete_local(
            block_id, version=version, allow_idempotent=True
        )


class ClusterBlockBridge:
    """Reads blocks from replica nodes; restores via replicate endpoints."""

    def __init__(
        self,
        node_client,
        get_addresses: Callable[[], Dict[str, str]],
        get_placements: Callable[[], Dict[str, List[str]]],
        placement_service=None,
    ):
        self._node_client = node_client
        self._get_addresses = get_addresses
        self._get_placements = get_placements
        self._placement_service = placement_service
        self._timeout = 10.0

    def list_blocks(self) -> List[str]:
        placements = self._get_placements()
        return sorted(placements.keys())

    def read_block(self, block_id: str) -> Optional[_BlockView]:
        placements = self._get_placements()
        nodes = placements.get(block_id, [])
        if not nodes:
            return None
        addresses = self._get_addresses()
        for node_id in nodes:
            try:
                record = self._node_client.read_block(node_id, block_id, addresses)
                if record:
                    return _BlockView(
                        block_id=block_id,
                        data=record.get("data", ""),
                        version=record.get("version", 1),
                        deleted=record.get("deleted", False),
                    )
            except Exception:
                log.debug("failed to read block from %s", node_id, exc_info=True)
        return None

    def write_local(self, block_id: str, data: str, version: int):
        self._replicate_to_nodes(block_id, data=data, version=version, delete=False)

    def delete_local(self, block_id: str, version: int):
        self._replicate_to_nodes(block_id, data=None, version=version, delete=True)

    def _replicate_to_nodes(
        self,
        block_id: str,
        data: Optional[str],
        version: int,
        delete: bool,
    ) -> None:
        placements = self._get_placements()
        nodes = placements.get(block_id, [])
        if not nodes and self._placement_service:
            nodes = self._placement_service.get_block_locations(block_id) or []
        addresses = self._get_addresses()
        with httpx.Client(timeout=self._timeout) as client:
            for node_id in nodes:
                url = f"{self._node_client.resolve_url(node_id, addresses)}"
                if delete:
                    endpoint = f"{url}/replicate-delete"
                    body = {"block_id": block_id, "version": version}
                else:
                    endpoint = f"{url}/replicate"
                    body = {
                        "block_id": block_id,
                        "data": data,
                        "version": version,
                        "origin_node_id": node_id,
                        "lsn": 0,
                    }
                try:
                    response = client.post(endpoint, json=body)
                    response.raise_for_status()
                except httpx.HTTPError:
                    log.warning(
                        "restore replicate failed",
                        extra={"node_id": node_id, "block_id": block_id},
                    )


def make_placement_restore(store, placement_registry=None):
    def restore_placement(block_id: str, version: int, nodes: List[str]) -> None:
        store.save_placement(block_id, version, nodes)
        if placement_registry is not None:
            placement_registry.register_block(block_id, version, nodes)

    return restore_placement
