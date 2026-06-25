"""Asynchronous read repair for stale replicas."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List

from node.metrics import Metrics
from node.replica_client import ReplicaClient, ReplicaClientError
from node.replication_models import ReplicateRequest
from node.version_reconciliation import ReplicaCopy

log = logging.getLogger(__name__)


class ReadRepair:

    def __init__(
        self,
        node_id: str,
        replica_client: ReplicaClient,
        metrics: Metrics,
        resolve_url_fn: Callable,
    ):
        self._node_id = node_id
        self._replica_client = replica_client
        self._metrics = metrics
        self._resolve_url = resolve_url_fn
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="read-repair")
        self._repair_count = 0
        self._lock = threading.Lock()

    @property
    def repair_count(self) -> int:
        with self._lock:
            return self._repair_count

    def repair_async(
        self,
        latest: ReplicaCopy,
        stale: List[ReplicaCopy],
        addresses: dict,
    ) -> None:
        if not stale:
            return
        self._executor.submit(self._repair_sync, latest, stale, addresses)

    def repair_sync(
        self,
        latest: ReplicaCopy,
        stale: List[ReplicaCopy],
        addresses: dict,
    ) -> int:
        return self._repair_sync(latest, stale, addresses)

    def _repair_sync(
        self,
        latest: ReplicaCopy,
        stale: List[ReplicaCopy],
        addresses: dict,
    ) -> int:
        repaired = 0
        for copy in stale:
            if copy.deleted:
                continue
            try:
                target_url = self._resolve_url(copy.node_id, addresses)
                request = ReplicateRequest(
                    block_id=latest.block_id,
                    data=latest.data,
                    version=latest.version,
                    lsn=latest.lsn,
                    origin_node_id=self._node_id,
                )
                self._replica_client.replicate_write(
                    target_url, copy.node_id, request
                )
                repaired += 1
                with self._lock:
                    self._repair_count += 1
                self._metrics.inc_read_repairs()
                log.info(
                    "read repair completed",
                    extra={
                        "block_id": latest.block_id,
                        "target": copy.node_id,
                        "version": latest.version,
                    },
                )
            except ReplicaClientError as exc:
                log.warning(
                    "read repair failed",
                    extra={"target": copy.node_id, "error": str(exc)},
                )
        return repaired

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
