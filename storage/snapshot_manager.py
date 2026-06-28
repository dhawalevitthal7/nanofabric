"""Copy-on-write snapshot manager."""

import logging
import threading
from typing import Callable, Dict, List, Optional, Protocol

from storage.metrics import ProtectionMetrics
from storage.models import SnapshotRecord, SnapshotStatus
from storage.snapshot_store import SnapshotStore

log = logging.getLogger(__name__)


class BlockReader(Protocol):
    def list_blocks(self) -> List[str]: ...
    def read_block(self, block_id: str): ...


class SnapshotManager:
    """Creates, restores, deletes, and lists point-in-time snapshots."""

    def __init__(
        self,
        store: SnapshotStore,
        read_blocks: BlockReader,
        get_metadata_version: Callable[[], int],
        get_placements: Callable[[], Dict[str, List[str]]],
        metrics: Optional[ProtectionMetrics] = None,
    ):
        self._store = store
        self._read_blocks = read_blocks
        self._get_metadata_version = get_metadata_version
        self._get_placements = get_placements
        self._metrics = metrics or ProtectionMetrics()
        self._lock = threading.Lock()

    def create_snapshot(self) -> SnapshotRecord:
        with self._lock:
            metadata_version = self._get_metadata_version()
            placements = self._get_placements()
            record = self._store.create_snapshot_record(metadata_version, placements)

            try:
                block_ids = self._read_blocks.list_blocks()
                size_bytes = 0
                for block_id in block_ids:
                    block = self._read_blocks.read_block(block_id)
                    if block is None:
                        continue
                    data = "" if block.deleted else block.data
                    if not block.deleted and data:
                        size_bytes += len(data.encode("utf-8"))
                    version_id = self._store.get_or_create_block_version(
                        block_id,
                        block.version,
                        None if block.deleted else data,
                        block.deleted,
                    )
                    self._store.add_snapshot_block(
                        record.snapshot_id, block_id, version_id
                    )

                finalized = self._store.finalize_snapshot(
                    record.snapshot_id,
                    block_count=len(block_ids),
                    size_bytes=size_bytes,
                    status=SnapshotStatus.READY,
                )
                self._metrics.inc_snapshots(size_bytes)
                log.info(
                    "snapshot created",
                    extra={
                        "snapshot_id": record.snapshot_id,
                        "blocks": len(block_ids),
                    },
                )
                return finalized or record
            except Exception as exc:
                self._store.finalize_snapshot(
                    record.snapshot_id,
                    block_count=0,
                    size_bytes=0,
                    status=SnapshotStatus.FAILED,
                    error=str(exc),
                )
                log.exception("snapshot creation failed")
                raise

    def list_snapshots(self) -> List[SnapshotRecord]:
        return self._store.list_snapshots()

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotRecord]:
        return self._store.get_snapshot(snapshot_id)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        with self._lock:
            snapshot = self._store.get_snapshot(snapshot_id)
            if not snapshot:
                return False
            result = self._store.delete_snapshot(snapshot_id)
            if isinstance(result, tuple):
                deleted, size_bytes = result
                if deleted:
                    self._metrics.dec_snapshots(size_bytes)
                return deleted
            return bool(result)

    def get_snapshot_blocks(self, snapshot_id: str) -> List[dict]:
        return self._store.get_snapshot_blocks(snapshot_id)

    def on_block_write(
        self,
        block_id: str,
        old_version: int,
        old_data: Optional[str],
        old_deleted: bool,
    ) -> None:
        """COW hook: preserve old version if referenced by any snapshot."""
        rows = self._store.conn.execute(
            """
            SELECT bv.version_id, bv.ref_count
            FROM block_versions bv
            WHERE bv.block_id = ? AND bv.version = ?
            """,
            (block_id, old_version),
        ).fetchall()
        if rows:
            return
        referenced = self._store.conn.execute(
            """
            SELECT 1 FROM snapshot_blocks sb
            JOIN block_versions bv ON sb.version_id = bv.version_id
            WHERE bv.block_id = ? AND bv.version = ?
            LIMIT 1
            """,
            (block_id, old_version),
        ).fetchone()
        if referenced:
            self._store.get_or_create_block_version(
                block_id, old_version, old_data, old_deleted
            )

    def recover(self) -> List[str]:
        return self._store.recover_interrupted_snapshots()
