"""Restore service — blocks, snapshots, metadata, and placements."""

import logging
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional, Protocol

from storage.metrics import ProtectionMetrics
from storage.models import RestoreJob, RestoreJobStatus, SnapshotStatus
from storage.snapshot_manager import SnapshotManager
from storage.snapshot_store import SnapshotStore

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class BlockWriter(Protocol):
    def write_local(self, block_id: str, data: str, version: int): ...
    def delete_local(self, block_id: str, version: int): ...
    def list_blocks(self) -> List[str]: ...


class RestoreService:
    """Restores snapshots and backups with crash recovery."""

    def __init__(
        self,
        store: SnapshotStore,
        snapshot_manager: SnapshotManager,
        write_blocks: BlockWriter,
        restore_placement: Callable[[str, int, List[str]], None],
        clear_blocks: Optional[Callable[[], None]] = None,
        metrics: Optional[ProtectionMetrics] = None,
    ):
        self._store = store
        self._snapshot_manager = snapshot_manager
        self._write_blocks = write_blocks
        self._restore_placement = restore_placement
        self._clear_blocks = clear_blocks
        self._metrics = metrics or ProtectionMetrics()
        self._lock = threading.Lock()

    def restore_snapshot(self, snapshot_id: str) -> RestoreJob:
        job = RestoreJob(
            job_id=str(uuid.uuid4()),
            source_type="snapshot",
            source_id=snapshot_id,
            status=RestoreJobStatus.RUNNING,
            created_at=_now_ms(),
        )
        self._store.save_restore_job(job)
        start = time.perf_counter()

        snapshot = self._store.get_snapshot(snapshot_id)
        if not snapshot:
            job.status = RestoreJobStatus.FAILED
            job.error = f"Snapshot '{snapshot_id}' not found"
            job.completed_at = _now_ms()
            self._store.save_restore_job(job)
            return job

        if snapshot.status not in (SnapshotStatus.READY, SnapshotStatus.FAILED):
            job.status = RestoreJobStatus.FAILED
            job.error = f"Snapshot status is {snapshot.status.value}"
            job.completed_at = _now_ms()
            self._store.save_restore_job(job)
            return job

        self._store.update_status(snapshot_id, SnapshotStatus.RESTORING)

        try:
            with self._lock:
                blocks = self._store.get_snapshot_blocks(snapshot_id)
                snapshot_block_ids = {b["block_id"] for b in blocks}

                if self._clear_blocks:
                    self._clear_blocks()

                for block in blocks:
                    block_id = block["block_id"]
                    version = block["version"]
                    if block["deleted"]:
                        self._write_blocks.delete_local(block_id, version)
                    else:
                        self._write_blocks.write_local(
                            block_id, block["data"] or "", version
                        )
                    job.blocks_restored += 1

                current_blocks = set(self._write_blocks.list_blocks())
                for block_id in current_blocks - snapshot_block_ids:
                    self._write_blocks.delete_local(block_id, 9999)

                for block_id, nodes in snapshot.placements.items():
                    self._restore_placement(block_id, 1, nodes)
                    job.placements_restored += 1

                elapsed_ms = (time.perf_counter() - start) * 1000
                job.status = RestoreJobStatus.COMPLETED
                job.completed_at = _now_ms()
                job.duration_ms = round(elapsed_ms, 3)
                self._store.update_status(snapshot_id, SnapshotStatus.READY)
                self._store.save_restore_job(job)
                self._metrics.inc_restore_jobs(elapsed_ms)
                log.info(
                    "snapshot restored",
                    extra={
                        "snapshot_id": snapshot_id,
                        "blocks": job.blocks_restored,
                    },
                )
                return job
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            job.status = RestoreJobStatus.FAILED
            job.error = str(exc)
            job.completed_at = _now_ms()
            job.duration_ms = round(elapsed_ms, 3)
            self._store.update_status(snapshot_id, SnapshotStatus.READY)
            self._store.save_restore_job(job)
            log.exception("snapshot restore failed")
            raise

    def list_restore_jobs(self) -> List[RestoreJob]:
        return self._store.list_restore_jobs()

    def get_restore_job(self, job_id: str) -> Optional[RestoreJob]:
        for job in self._store.list_restore_jobs():
            if job.job_id == job_id:
                return job
        return None

    def restore_backup(
        self,
        backup_id: str,
        backup_service,
    ) -> RestoreJob:
        job = RestoreJob(
            job_id=str(uuid.uuid4()),
            source_type="backup",
            source_id=backup_id,
            status=RestoreJobStatus.RUNNING,
            created_at=_now_ms(),
        )
        self._store.save_restore_job(job)
        start = time.perf_counter()

        try:
            metadata, blocks = backup_service.extract_backup_blocks(backup_id)
            placements = metadata.get("placements", {})

            if self._clear_blocks:
                self._clear_blocks()

            for block in blocks:
                block_id = block["block_id"]
                version = block["version"]
                if block.get("deleted"):
                    self._write_blocks.delete_local(block_id, version)
                else:
                    self._write_blocks.write_local(
                        block_id, block.get("data", ""), version
                    )
                job.blocks_restored += 1

            for block_id, nodes in placements.items():
                self._restore_placement(block_id, 1, nodes)
                job.placements_restored += 1

            elapsed_ms = (time.perf_counter() - start) * 1000
            job.status = RestoreJobStatus.COMPLETED
            job.completed_at = _now_ms()
            job.duration_ms = round(elapsed_ms, 3)
            self._store.save_restore_job(job)
            self._metrics.inc_restore_jobs(elapsed_ms)
            return job
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            job.status = RestoreJobStatus.FAILED
            job.error = str(exc)
            job.completed_at = _now_ms()
            job.duration_ms = round(elapsed_ms, 3)
            self._store.save_restore_job(job)
            raise

    def recover_interrupted_restores(self) -> None:
        for job in self._store.list_restore_jobs():
            if job.status == RestoreJobStatus.RUNNING:
                job.status = RestoreJobStatus.FAILED
                job.error = "interrupted — recovered on startup"
                job.completed_at = _now_ms()
                self._store.save_restore_job(job)
