import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from node.cache import Cache
from node.errors import VersionConflictError
from node.extent_store import ExtentStore
from node.manifest import Manifest
from node.metrics import Metrics
from node.op_types import OpType
from node.oplog import Oplog
from node.validation import validate_delete, validate_write

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlockRecord:
    block_id: str
    data: str
    version: int
    deleted: bool = False
    origin_node_id: Optional[str] = None
    origin_lsn: Optional[int] = None


class StorageEngine:

    def __init__(
        self,
        data_dir,
        node_id="node1",
        fsync_policy="always",
        cache_max_entries=10_000,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.node_id = node_id
        self._lock = threading.Lock()
        self._closed = False
        self._last_checkpoint_lsn = 0

        self.metrics = Metrics()
        self.cache = Cache(max_entries=cache_max_entries)
        self.oplog = Oplog(
            self.data_dir / "oplog.jsonl",
            node_id=node_id,
            metrics=self.metrics,
            fsync_policy=fsync_policy,
        )
        self.db = ExtentStore(self.data_dir / "extent_store.db")
        self.manifest = Manifest(self.data_dir / "manifest.json")

        manifest_data = self.manifest.load()
        self._last_checkpoint_lsn = manifest_data.get("last_checkpoint_lsn", 0)

        self.oplog.recover()
        self._replay_oplog()
        self._update_manifest()

    def _resolve_write_version(self, block_id, version):
        current = self.db.get_row(block_id)
        current_version = current["version"] if current else 0

        if version is None:
            return current_version + 1

        if version <= current_version:
            raise VersionConflictError(block_id, version, current_version)
        return version

    def _resolve_delete_version(self, block_id):
        current = self.db.get_row(block_id)
        return (current["version"] if current else 0) + 1

    def _record_to_cache(self, row):
        return {
            "block_id": row["block_id"],
            "data": row["data"],
            "version": row["version"],
            "deleted": bool(row["deleted"]),
            "origin_node_id": row.get("origin_node_id"),
            "origin_lsn": row.get("origin_lsn"),
        }

    def _apply_write_entry(self, entry, commit=True):
        block_id = entry["block_id"]
        version = entry.get("version", 1)
        data = entry["data"]
        origin_node_id = entry.get("node_id")
        origin_lsn = entry.get("lsn")

        self.db.save_if_newer(
            block_id,
            data,
            version,
            origin_node_id=origin_node_id,
            origin_lsn=origin_lsn,
            updated_at_ms=entry.get("ts_ms"),
        )
        if commit:
            self.db.conn.commit()

        row = self.db.get_row(block_id)
        if row and not row["deleted"]:
            self.cache.put(block_id, self._record_to_cache(row))

    def _apply_delete_entry(self, entry, commit=True):
        block_id = entry["block_id"]
        version = entry.get("version", 1)

        self.db.tombstone_if_newer(
            block_id,
            version,
            origin_node_id=entry.get("node_id"),
            origin_lsn=entry.get("lsn"),
            deleted_at_ms=entry.get("ts_ms"),
        )
        if commit:
            self.db.conn.commit()

        self.cache.remove(block_id)

    def _apply_entry(self, entry, commit=True):
        op = entry.get("op")
        if op == OpType.WRITE:
            self._apply_write_entry(entry, commit=commit)
        elif op == OpType.DELETE:
            self._apply_delete_entry(entry, commit=commit)
        elif op == OpType.CHECKPOINT:
            through_lsn = entry.get("through_lsn", 0)
            if through_lsn > self._last_checkpoint_lsn:
                self._last_checkpoint_lsn = through_lsn

    def _replay_oplog(self):
        applied_lsn = self.db.get_replay_cursor()
        replayed = 0

        with self.db.transaction():
            for entry in self.oplog.iter_entries():
                lsn = entry.get("lsn", 0)
                if lsn and lsn <= applied_lsn:
                    continue
                self._apply_entry(entry, commit=False)
                if lsn:
                    applied_lsn = lsn
                replayed += 1

            self.db.set_replay_cursor(applied_lsn, commit=False)

        self.metrics.inc_replay(replayed)
        log.info(
            "oplog replay complete",
            extra={
                "node_id": self.node_id,
                "entries": replayed,
                "last_lsn": applied_lsn,
            },
        )

    def _update_manifest(self):
        self.manifest.save(
            self.node_id,
            self.oplog.high_water_lsn,
            self._last_checkpoint_lsn,
            self.db.count_blocks(),
        )

    def write(self, block_id, data, version=None):
        self._ensure_open()
        validate_write(block_id, data, version)

        with self._lock:
            resolved_version = self._resolve_write_version(block_id, version)
            lsn = self.oplog.append(
                OpType.WRITE,
                block_id,
                data=data,
                version=resolved_version,
            )
            self._apply_write_entry(
                {
                    "block_id": block_id,
                    "data": data,
                    "version": resolved_version,
                    "node_id": self.node_id,
                    "lsn": lsn,
                    "ts_ms": None,
                },
            )
            self._update_manifest()
            self.metrics.inc_writes()
            return True

    def read(self, block_id):
        record = self.read_block(block_id)
        return record.data if record and not record.deleted else None

    def read_block(self, block_id):
        self._ensure_open()

        with self._lock:
            cached = self.cache.get(block_id)
            if cached is not None:
                self.metrics.inc_reads(cache_hit=True)
                if cached["deleted"]:
                    return BlockRecord(
                        block_id=block_id,
                        data="",
                        version=cached["version"],
                        deleted=True,
                        origin_node_id=cached.get("origin_node_id"),
                        origin_lsn=cached.get("origin_lsn"),
                    )
                return BlockRecord(
                    block_id=block_id,
                    data=cached["data"],
                    version=cached["version"],
                    deleted=False,
                    origin_node_id=cached.get("origin_node_id"),
                    origin_lsn=cached.get("origin_lsn"),
                )

            row = self.db.get_row(block_id)
            self.metrics.inc_reads(cache_hit=False)
            if not row or row["deleted"]:
                return None

            cache_record = self._record_to_cache(row)
            self.cache.put(block_id, cache_record)
            return BlockRecord(
                block_id=block_id,
                data=row["data"],
                version=row["version"],
                deleted=False,
                origin_node_id=row.get("origin_node_id"),
                origin_lsn=row.get("origin_lsn"),
            )

    def delete(self, block_id):
        self._ensure_open()
        validate_delete(block_id)

        with self._lock:
            version = self._resolve_delete_version(block_id)
            lsn = self.oplog.append(
                OpType.DELETE,
                block_id,
                data=None,
                version=version,
            )
            self._apply_delete_entry(
                {
                    "block_id": block_id,
                    "version": version,
                    "node_id": self.node_id,
                    "lsn": lsn,
                    "ts_ms": None,
                },
            )
            self._update_manifest()
            self.metrics.inc_deletes()
            return True

    def list_blocks(self):
        self._ensure_open()
        with self._lock:
            return self.db.list_blocks()

    def checkpoint(self, through_lsn=None):
        """Record checkpoint and compact oplog entries at or below through_lsn."""
        self._ensure_open()
        with self._lock:
            lsn = through_lsn or self.oplog.high_water_lsn
            self.oplog.append(
                OpType.CHECKPOINT,
                block_id="",
                version=0,
                through_lsn=lsn,
            )
            self._last_checkpoint_lsn = lsn
            self.oplog.compact(lsn)
            self.db.set_replay_cursor(lsn)
            self._update_manifest()
            return lsn

    def get_stats(self):
        self._ensure_open()
        with self._lock:
            oplog_bytes = (
                self.oplog.path.stat().st_size
                if self.oplog.path.exists()
                else 0
            )
            stats = {
                "node_id": self.node_id,
                "block_count": self.db.count_blocks(),
                "oplog_bytes": oplog_bytes,
                "last_lsn": self.oplog.high_water_lsn,
                "last_checkpoint_lsn": self._last_checkpoint_lsn,
                "cache_entries": len(self.cache),
            }
            stats.update(self.metrics.snapshot())
            return stats

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._update_manifest()
            self.oplog.close()
            self.db.close()
            self._closed = True

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("StorageEngine is closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
