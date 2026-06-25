"""Coordinates distributed quorum reads across replicas."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional

from node.consistency import ConsistencyLevel
from node.metadata_client import MetadataClient
from node.metrics import Metrics
from node.quorum import is_quorum_satisfied, required_reads
from node.quorum_manager import QuorumOutcome
from node.read_repair import ReadRepair
from node.replica_client import ReplicaClient, ReplicaClientError
from node.storage_engine import BlockRecord, StorageEngine
from node.version_reconciliation import ReplicaCopy, find_stale_replicas, select_latest

log = logging.getLogger(__name__)


@dataclass
class ReadResult:
    block_id: str
    data: str
    version: int
    node_id: str
    quorum_satisfied: bool
    copies_read: int
    outcome: str


class ReadCoordinator:

    def __init__(
        self,
        node_id: str,
        engine: StorageEngine,
        metadata_client: MetadataClient,
        replica_client: ReplicaClient,
        read_repair: ReadRepair,
        metrics: Metrics,
        consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ):
        self._node_id = node_id
        self._engine = engine
        self._metadata = metadata_client
        self._replica_client = replica_client
        self._read_repair = read_repair
        self._metrics = metrics
        self._consistency = consistency

    @property
    def consistency(self) -> ConsistencyLevel:
        return self._consistency

    def set_consistency(self, level: ConsistencyLevel) -> None:
        self._consistency = level

    def read(
        self,
        block_id: str,
        consistency: Optional[ConsistencyLevel] = None,
        repair: bool = True,
    ) -> Optional[ReadResult]:
        level = consistency or self._consistency
        locations = self._metadata.get_block_locations(block_id)
        if not locations:
            return self._read_local_only(block_id, level)

        rf = len(locations)
        required = required_reads(rf, level)
        copies = self._read_from_replicas(block_id, locations)

        if not copies:
            self._metrics.inc_read_quorum_failures()
            return None

        successful = [c for c in copies if c.version > 0 or not c.deleted]
        if is_quorum_satisfied(len(successful), required):
            latest = select_latest(successful)
            if latest is None:
                return None

            if repair and len(successful) > 1:
                stale = find_stale_replicas(successful, latest)
                if stale:
                    addresses = self._metadata.get_node_addresses()
                    self._read_repair.repair_async(latest, stale, addresses)

            return ReadResult(
                block_id=latest.block_id,
                data=latest.data,
                version=latest.version,
                node_id=latest.node_id,
                quorum_satisfied=True,
                copies_read=len(successful),
                outcome=QuorumOutcome.SUCCESS.value,
            )

        self._metrics.inc_read_quorum_failures()
        latest = select_latest(copies)
        if latest is None:
            return None
        return ReadResult(
            block_id=latest.block_id,
            data=latest.data,
            version=latest.version,
            node_id=latest.node_id,
            quorum_satisfied=False,
            copies_read=len(successful),
            outcome=QuorumOutcome.FAILED.value,
        )

    def _read_local_only(
        self, block_id: str, level: ConsistencyLevel
    ) -> Optional[ReadResult]:
        record = self._engine.read_block(block_id)
        if record is None or record.deleted:
            return None
        return ReadResult(
            block_id=record.block_id,
            data=record.data,
            version=record.version,
            node_id=self._node_id,
            quorum_satisfied=True,
            copies_read=1,
            outcome=QuorumOutcome.SUCCESS.value,
        )

    def _read_from_replicas(
        self, block_id: str, locations: List[str]
    ) -> List[ReplicaCopy]:
        copies: List[ReplicaCopy] = []
        addresses = self._metadata.get_node_addresses()

        def read_node(node_id: str) -> Optional[ReplicaCopy]:
            if node_id == self._node_id:
                record = self._engine.read_block(block_id)
                if record is None:
                    return None
                return self._record_to_copy(node_id, record)
            try:
                url = self._metadata.resolve_node_url(node_id, addresses)
                response = self._replica_client.read_block(url, node_id, block_id)
                if response is None:
                    return None
                return ReplicaCopy(
                    node_id=node_id,
                    block_id=block_id,
                    data=response.get("data", ""),
                    version=response.get("version", 0),
                    lsn=response.get("origin_lsn") or response.get("lsn", 0),
                    timestamp_ms=response.get("updated_at_ms", 0),
                    deleted=response.get("deleted", False),
                )
            except ReplicaClientError:
                return None

        with ThreadPoolExecutor(max_workers=len(locations)) as pool:
            futures = {pool.submit(read_node, nid): nid for nid in locations}
            for future in as_completed(futures):
                try:
                    copy = future.result()
                    if copy is not None:
                        copies.append(copy)
                except Exception:
                    log.exception("read from replica failed")

        return copies

    def _record_to_copy(self, node_id: str, record: BlockRecord) -> ReplicaCopy:
        row = self._engine.db.get_row(record.block_id)
        ts = row.get("updated_at_ms", 0) if row else 0
        return ReplicaCopy(
            node_id=node_id,
            block_id=record.block_id,
            data=record.data,
            version=record.version,
            lsn=record.origin_lsn or 0,
            timestamp_ms=ts or 0,
            deleted=record.deleted,
        )

    def get_quorum_status(self, block_id: str) -> dict:
        locations = self._metadata.get_block_locations(block_id)
        rf = len(locations) if locations else 1
        from node.quorum import calculate_read_quorum, calculate_write_quorum

        return {
            "block_id": block_id,
            "replication_factor": rf,
            "locations": locations or [],
            "write_quorum": calculate_write_quorum(rf),
            "read_quorum": calculate_read_quorum(rf),
            "consistency": self._consistency.value,
        }
