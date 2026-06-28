"""Backup service — full/incremental backups with zip export."""

import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from storage.metrics import ProtectionMetrics
from storage.models import BackupRecord, BackupStatus, BackupType
from storage.snapshot_manager import SnapshotManager
from storage.snapshot_store import SnapshotStore

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_block_filename(block_id: str, version: int) -> str:
    safe_id = block_id.replace(":", "_").replace("/", "_").replace("\\", "_")
    return f"{safe_id}__v{version}.json"


class BackupService:
    """Creates full and incremental backups; exports and imports zip archives."""

    def __init__(
        self,
        store: SnapshotStore,
        snapshot_manager: SnapshotManager,
        backup_dir: str | Path,
        get_placements: Callable[[], Dict[str, List[str]]],
        get_metadata_version: Callable[[], int],
        metrics: Optional[ProtectionMetrics] = None,
    ):
        self._store = store
        self._snapshot_manager = snapshot_manager
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._get_placements = get_placements
        self._get_metadata_version = get_metadata_version
        self._metrics = metrics or ProtectionMetrics()
        self._lock = threading.Lock()

    def create_backup(
        self,
        backup_type: BackupType = BackupType.FULL,
        base_backup_id: Optional[str] = None,
        snapshot_ids: Optional[List[str]] = None,
    ) -> BackupRecord:
        with self._lock:
            backup_id = str(uuid.uuid4())
            now = _now_ms()
            record = BackupRecord(
                backup_id=backup_id,
                backup_type=backup_type,
                timestamp=now,
                status=BackupStatus.CREATING,
                base_backup_id=base_backup_id,
            )
            self._store.save_backup(record)

            try:
                if not snapshot_ids:
                    snap = self._snapshot_manager.create_snapshot()
                    snapshot_ids = [snap.snapshot_id]
                record.snapshot_ids = snapshot_ids

                work_dir = self._backup_dir / backup_id
                work_dir.mkdir(parents=True, exist_ok=True)
                blocks_dir = work_dir / "blocks"
                snapshots_dir = work_dir / "snapshots"
                blocks_dir.mkdir(exist_ok=True)
                snapshots_dir.mkdir(exist_ok=True)

                base_blocks: Dict[str, dict] = {}
                if backup_type == BackupType.INCREMENTAL and base_backup_id:
                    base = self._store.get_backup(base_backup_id)
                    if base and base.archive_path:
                        base_blocks = self._load_blocks_from_archive(base.archive_path)

                all_blocks: Dict[str, dict] = {}
                for sid in snapshot_ids:
                    snap = self._store.get_snapshot(sid)
                    if not snap:
                        continue
                    snap_path = snapshots_dir / f"{sid}.json"
                    snap_path.write_text(snap.model_dump_json(), encoding="utf-8")
                    for block in self._store.get_snapshot_blocks(sid):
                        key = f"{block['block_id']}:{block['version']}"
                        if backup_type == BackupType.INCREMENTAL:
                            if key in base_blocks:
                                continue
                        all_blocks[key] = block

                block_count = 0
                size_bytes = 0
                for block in all_blocks.values():
                    payload = {
                        "block_id": block["block_id"],
                        "version": block["version"],
                        "data": block["data"],
                        "deleted": bool(block["deleted"]),
                    }
                    content = json.dumps(payload)
                    block_file = blocks_dir / _safe_block_filename(
                        block["block_id"], block["version"]
                    )
                    block_file.write_text(content, encoding="utf-8")
                    block_count += 1
                    size_bytes += len(content.encode("utf-8"))

                metadata = {
                    "backup_id": backup_id,
                    "backup_type": backup_type.value,
                    "timestamp": now,
                    "snapshot_ids": snapshot_ids,
                    "metadata_version": self._get_metadata_version(),
                    "placements": self._get_placements(),
                    "block_count": block_count,
                    "checksum": "",
                }
                metadata_path = work_dir / "metadata.json"
                metadata_path.write_text(
                    json.dumps(metadata, indent=2), encoding="utf-8"
                )

                archive_path = self._backup_dir / f"{backup_id}.zip"
                self._create_zip(work_dir, archive_path)
                size_bytes += archive_path.stat().st_size

                shutil.rmtree(work_dir, ignore_errors=True)

                record.block_count = block_count
                record.size_bytes = size_bytes
                record.archive_path = str(archive_path)
                record.status = BackupStatus.READY
                self._store.save_backup(record)
                self._metrics.inc_backups()
                log.info(
                    "backup created",
                    extra={"backup_id": backup_id, "type": backup_type.value},
                )
                return record
            except Exception as exc:
                record.status = BackupStatus.FAILED
                record.error = str(exc)
                self._store.save_backup(record)
                log.exception("backup creation failed")
                raise

    def list_backups(self) -> List[BackupRecord]:
        return self._store.list_backups()

    def get_backup(self, backup_id: str) -> Optional[BackupRecord]:
        return self._store.get_backup(backup_id)

    def import_backup(self, archive_path: str | Path) -> BackupRecord:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise FileNotFoundError(f"Backup archive not found: {archive_path}")

        with zipfile.ZipFile(archive_path, "r") as zf:
            metadata = json.loads(zf.read("metadata.json"))
            if self._verify_checksum(zf, metadata):
                pass

            backup_id = metadata.get("backup_id", str(uuid.uuid4()))
            record = BackupRecord(
                backup_id=backup_id,
                backup_type=BackupType(metadata.get("backup_type", "FULL")),
                timestamp=metadata.get("timestamp", _now_ms()),
                snapshot_ids=metadata.get("snapshot_ids", []),
                block_count=metadata.get("block_count", 0),
                status=BackupStatus.READY,
                archive_path=str(archive_path),
            )
            self._store.save_backup(record)
            return record

    def extract_backup_blocks(self, backup_id: str) -> tuple[dict, List[dict]]:
        backup = self._store.get_backup(backup_id)
        if not backup or not backup.archive_path:
            raise FileNotFoundError(f"Backup '{backup_id}' not found")

        blocks = []
        metadata = {}
        with zipfile.ZipFile(backup.archive_path, "r") as zf:
            metadata = json.loads(zf.read("metadata.json"))
            for name in zf.namelist():
                if name.startswith("blocks/") and name.endswith(".json"):
                    blocks.append(json.loads(zf.read(name)))

            for name in zf.namelist():
                if name.startswith("snapshots/") and name.endswith(".json"):
                    snap_data = json.loads(zf.read(name))
                    sid = snap_data.get("snapshot_id")
                    if sid and sid not in metadata.get("snapshot_ids", []):
                        metadata.setdefault("snapshot_ids", []).append(sid)

        return metadata, blocks

    def _create_zip(self, source_dir: Path, archive_path: Path) -> None:
        metadata_path = source_dir / "metadata.json"
        meta = {}
        if metadata_path.exists():
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))

        h = hashlib.sha256()
        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file() and file_path.name != "metadata.json":
                arcname = file_path.relative_to(source_dir).as_posix()
                h.update(arcname.encode())
                h.update(file_path.read_bytes())
        meta["checksum"] = h.hexdigest()

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(source_dir.rglob("*")):
                if file_path.is_file() and file_path.name != "metadata.json":
                    arcname = file_path.relative_to(source_dir).as_posix()
                    zf.write(file_path, arcname)
            zf.writestr("metadata.json", json.dumps(meta, indent=2))

    def _compute_archive_checksum(self, zf: zipfile.ZipFile) -> str:
        h = hashlib.sha256()
        for name in sorted(zf.namelist()):
            if name == "metadata.json":
                continue
            normalized = name.replace("\\", "/")
            h.update(normalized.encode())
            h.update(zf.read(name))
        return h.hexdigest()

    def _verify_checksum(self, zf: zipfile.ZipFile, metadata: dict) -> bool:
        expected = metadata.get("checksum", "")
        if not expected:
            return True
        actual = self._compute_archive_checksum(zf)
        if actual != expected:
            log.warning(
                "backup checksum mismatch",
                extra={"expected": expected, "actual": actual},
            )
            return False
        return True

    def _load_blocks_from_archive(self, archive_path: str) -> Dict[str, dict]:
        result = {}
        with zipfile.ZipFile(archive_path, "r") as zf:
            for name in zf.namelist():
                if name.startswith("blocks/") and name.endswith(".json"):
                    block = json.loads(zf.read(name))
                    key = f"{block['block_id']}:{block['version']}"
                    result[key] = block
        return result

    def recover_interrupted_backups(self) -> None:
        for backup in self._store.list_backups():
            if backup.status == BackupStatus.CREATING:
                backup.status = BackupStatus.FAILED
                backup.error = "interrupted — recovered on startup"
                self._store.save_backup(backup)
