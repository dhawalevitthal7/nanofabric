"""Retention manager — expire snapshots and reclaim orphan blocks."""

import logging
from typing import List, Optional

from storage.metrics import ProtectionMetrics
from storage.snapshot_manager import SnapshotManager
from storage.snapshot_store import SnapshotStore

log = logging.getLogger(__name__)


class RetentionManager:
    """Expires old snapshots and cleans orphan block versions."""

    def __init__(
        self,
        store: SnapshotStore,
        snapshot_manager: SnapshotManager,
        metrics: Optional[ProtectionMetrics] = None,
    ):
        self._store = store
        self._snapshot_manager = snapshot_manager
        self._metrics = metrics or ProtectionMetrics()

    def enforce_retention(self, keep_last_n: int) -> List[str]:
        snapshots = self._store.list_snapshots()
        ready = [s for s in snapshots if s.status.value == "READY"]
        ready.sort(key=lambda s: s.timestamp, reverse=True)

        expired = []
        for snapshot in ready[keep_last_n:]:
            size = snapshot.size_bytes
            if self._snapshot_manager.delete_snapshot(snapshot.snapshot_id):
                expired.append(snapshot.snapshot_id)
                log.info(
                    "snapshot expired by retention",
                    extra={"snapshot_id": snapshot.snapshot_id},
                )
        return expired

    def clean_orphan_blocks(self) -> int:
        reclaimed = self._store.reclaim_orphan_blocks()
        if reclaimed:
            log.info("orphan blocks reclaimed", extra={"count": reclaimed})
        return reclaimed

    def run_cleanup(self, retention_count: int = 7) -> dict:
        expired = self.enforce_retention(retention_count)
        orphans = self.clean_orphan_blocks()
        return {"expired_snapshots": expired, "orphan_blocks_reclaimed": orphans}
