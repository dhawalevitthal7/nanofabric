"""Restore missing replicas by streaming from a healthy source."""

import logging
import time
from typing import Callable, Dict, List, Optional

from cluster.node_client import NodeClient, NodeClientError
from cluster.repair_models import RepairType
from node.replica_client import ReplicaClient, ReplicaClientError
from node.replication_models import ReplicateRequest

log = logging.getLogger(__name__)


class ReReplicationService:

    def __init__(
        self,
        node_id: str,
        replica_client: ReplicaClient,
        node_client: NodeClient,
        get_node_addresses_fn: Callable[[], Dict[str, str]],
        get_block_locations_fn: Callable[[str], Optional[List[str]]],
        replace_replica_fn: Callable[[str, str, str, int], List[str]],
        select_replacement_fn: Callable[[str, List[str], List[str]], Optional[str]],
        get_healthy_nodes_fn: Optional[Callable[[], List[str]]] = None,
        metrics=None,
    ):
        self._node_id = node_id
        self._replica_client = replica_client
        self._node_client = node_client
        self._get_node_addresses = get_node_addresses_fn
        self._get_block_locations = get_block_locations_fn
        self._replace_replica = replace_replica_fn
        self._select_replacement = select_replacement_fn
        self._get_healthy_nodes = get_healthy_nodes_fn or (lambda: [])
        self._metrics = metrics

    def repair_block(
        self,
        block_id: str,
        version: int,
        source_node: Optional[str] = None,
        target_node: Optional[str] = None,
        repair_type: RepairType = RepairType.RE_REPLICATION,
    ) -> dict:
        addresses = self._get_node_addresses()
        locations = self._get_block_locations(block_id) or []

        source = source_node or self._select_source(block_id, locations, addresses)
        if not source:
            return {"ok": False, "error": "no source replica found"}

        target = target_node or self._select_replacement(
            block_id, locations, list(addresses.keys())
        )
        if not target:
            return {"ok": False, "error": "no replacement node available"}

        start = time.perf_counter()
        copied = self.copy_block(block_id, source, target, version, addresses)
        if not copied:
            return {"ok": False, "error": "copy failed", "source": source, "target": target}

        verified = self.verify_copy(block_id, source, target, addresses)
        if not verified:
            return {"ok": False, "error": "verification failed", "source": source, "target": target}

        locations = self._get_block_locations(block_id) or []
        healthy = set(self._get_healthy_nodes())
        missing = self._find_missing_node(
            block_id, locations, unhealthy=set(locations) - healthy
        )
        updated_nodes = self.update_metadata(
            block_id, source, target, version, locations, missing_node=missing
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if self._metrics:
            self._metrics.record_repair_latency(elapsed_ms)
            self._metrics.inc_blocks_rebuilt()

        return {
            "ok": True,
            "block_id": block_id,
            "source": source,
            "target": target,
            "nodes": updated_nodes,
            "repair_type": repair_type.value,
            "latency_ms": round(elapsed_ms, 3),
        }

    def copy_block(
        self,
        block_id: str,
        source_node: str,
        target_node: str,
        version: int,
        addresses: Optional[Dict[str, str]] = None,
    ) -> bool:
        addresses = addresses or self._get_node_addresses()
        try:
            record = self._node_client.read_block(source_node, block_id, addresses)
            if record is None or record.get("deleted"):
                return False

            source_url = self._node_client.resolve_url(source_node, addresses)
            target_url = self._node_client.resolve_url(target_node, addresses)
            request = ReplicateRequest(
                block_id=block_id,
                data=record["data"],
                version=record.get("version", version),
                lsn=record.get("origin_lsn", 0),
                origin_node_id=source_node,
            )
            self._replica_client.replicate_write(target_url, target_node, request)
            return True
        except (NodeClientError, ReplicaClientError) as exc:
            log.warning(
                "copy_block failed",
                extra={"block_id": block_id, "error": str(exc)},
            )
            return False

    def verify_copy(
        self,
        block_id: str,
        source_node: str,
        target_node: str,
        addresses: Optional[Dict[str, str]] = None,
    ) -> bool:
        addresses = addresses or self._get_node_addresses()
        try:
            source = self._node_client.read_block(source_node, block_id, addresses)
            target = self._node_client.read_block(target_node, block_id, addresses)
            if source is None or target is None:
                return False
            return (
                source.get("data") == target.get("data")
                and source.get("version") == target.get("version")
            )
        except NodeClientError:
            return False

    def update_metadata(
        self,
        block_id: str,
        source_node: str,
        target_node: str,
        version: int,
        locations: Optional[List[str]] = None,
        missing_node: Optional[str] = None,
    ) -> List[str]:
        locations = locations or self._get_block_locations(block_id) or []
        old_node = missing_node or self._find_missing_node(block_id, locations)
        if old_node and old_node != target_node:
            return self._replace_replica(block_id, old_node, target_node, version)
        if target_node not in locations:
            new_locations = list(locations) + [target_node]
            return self._replace_replica(block_id, locations[0], target_node, version)
        return locations

    def _select_source(
        self,
        block_id: str,
        locations: List[str],
        addresses: Dict[str, str],
    ) -> Optional[str]:
        for node_id in locations:
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

    def _find_missing_node(
        self,
        block_id: str,
        locations: List[str],
        unhealthy: Optional[set] = None,
    ) -> Optional[str]:
        addresses = self._get_node_addresses()
        for node_id in locations:
            if unhealthy and node_id in unhealthy:
                return node_id
        for node_id in locations:
            try:
                if not self._node_client.has_block(node_id, block_id, addresses):
                    return node_id
            except NodeClientError:
                return node_id
        return None
