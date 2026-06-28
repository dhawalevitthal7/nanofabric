"""SQLite-backed snapshot store with copy-on-write block references."""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from storage.models import SnapshotRecord, SnapshotStatus


def _now_ms() -> int:
    return int(time.time() * 1000)


class SnapshotStore:
    """Persists snapshot metadata and COW block references in snapshots.db."""

    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            block_count INTEGER NOT NULL DEFAULT 0,
            metadata_version INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'READY',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            placements_json TEXT NOT NULL DEFAULT '{}',
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS block_versions (
            version_id TEXT PRIMARY KEY,
            block_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            data TEXT,
            deleted INTEGER NOT NULL DEFAULT 0,
            ref_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(block_id, version)
        );

        CREATE TABLE IF NOT EXISTS snapshot_blocks (
            snapshot_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, block_id),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            FOREIGN KEY (version_id) REFERENCES block_versions(version_id)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshot_blocks_version
            ON snapshot_blocks(version_id);
        CREATE INDEX IF NOT EXISTS idx_block_versions_block
            ON block_versions(block_id);
        """)
        self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def create_snapshot_record(
        self,
        metadata_version: int,
        placements: Dict[str, List[str]],
    ) -> SnapshotRecord:
        snapshot_id = str(uuid.uuid4())
        now = _now_ms()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO snapshots(
                    snapshot_id, timestamp, block_count, metadata_version,
                    status, size_bytes, placements_json
                ) VALUES (?, ?, 0, ?, ?, 0, ?)
                """,
                (
                    snapshot_id,
                    now,
                    metadata_version,
                    SnapshotStatus.CREATING.value,
                    json.dumps(placements),
                ),
            )
            self.conn.commit()
        return SnapshotRecord(
            snapshot_id=snapshot_id,
            timestamp=now,
            block_count=0,
            metadata_version=metadata_version,
            status=SnapshotStatus.CREATING,
            placements=placements,
        )

    def get_or_create_block_version(
        self,
        block_id: str,
        version: int,
        data: Optional[str],
        deleted: bool,
    ) -> str:
        """Return version_id; reuse existing COW entry when present."""
        with self._lock:
            row = self.conn.execute(
                """
                SELECT version_id FROM block_versions
                WHERE block_id = ? AND version = ?
                """,
                (block_id, version),
            ).fetchone()
            if row:
                version_id = row["version_id"]
                self.conn.execute(
                    "UPDATE block_versions SET ref_count = ref_count + 1 WHERE version_id = ?",
                    (version_id,),
                )
                self.conn.commit()
                return version_id

            version_id = str(uuid.uuid4())
            self.conn.execute(
                """
                INSERT INTO block_versions(
                    version_id, block_id, version, data, deleted, ref_count
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (version_id, block_id, version, data, int(deleted)),
            )
            self.conn.commit()
            return version_id

    def add_snapshot_block(
        self,
        snapshot_id: str,
        block_id: str,
        version_id: str,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO snapshot_blocks(snapshot_id, block_id, version_id)
                VALUES (?, ?, ?)
                """,
                (snapshot_id, block_id, version_id),
            )
            self.conn.commit()

    def finalize_snapshot(
        self,
        snapshot_id: str,
        block_count: int,
        size_bytes: int,
        status: SnapshotStatus = SnapshotStatus.READY,
        error: Optional[str] = None,
    ) -> Optional[SnapshotRecord]:
        with self._lock:
            self.conn.execute(
                """
                UPDATE snapshots
                SET block_count = ?, size_bytes = ?, status = ?, error = ?
                WHERE snapshot_id = ?
                """,
                (block_count, size_bytes, status.value, error, snapshot_id),
            )
            self.conn.commit()
        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotRecord]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_snapshots(self) -> List[SnapshotRecord]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM snapshots ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_snapshot_blocks(self, snapshot_id: str) -> List[dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT sb.block_id, bv.version, bv.data, bv.deleted
                FROM snapshot_blocks sb
                JOIN block_versions bv ON sb.version_id = bv.version_id
                WHERE sb.snapshot_id = ?
                ORDER BY sb.block_id
                """,
                (snapshot_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        with self._lock:
            version_ids = [
                row["version_id"]
                for row in self.conn.execute(
                    "SELECT version_id FROM snapshot_blocks WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchall()
            ]
            row = self.conn.execute(
                "SELECT size_bytes FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if not row:
                return False
            size_bytes = row["size_bytes"]

            self.conn.execute(
                "DELETE FROM snapshot_blocks WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            self.conn.execute(
                "DELETE FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            for vid in version_ids:
                self.conn.execute(
                    "UPDATE block_versions SET ref_count = ref_count - 1 WHERE version_id = ?",
                    (vid,),
                )
            self.conn.execute(
                "DELETE FROM block_versions WHERE ref_count <= 0"
            )
            self.conn.commit()
        return True, size_bytes

    def get_snapshot_size(self, snapshot_id: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT size_bytes FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return row["size_bytes"] if row else 0

    def count_orphan_block_versions(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS cnt FROM block_versions WHERE ref_count <= 0"
            ).fetchone()
        return row["cnt"]

    def reclaim_orphan_blocks(self) -> int:
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM block_versions WHERE ref_count <= 0"
            )
            self.conn.commit()
            return cursor.rowcount

    def recover_interrupted_snapshots(self) -> List[str]:
        """Mark CREATING/RESTORING snapshots as FAILED after crash."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT snapshot_id FROM snapshots
                WHERE status IN ('CREATING', 'RESTORING', 'DELETING')
                """
            ).fetchall()
            ids = [row["snapshot_id"] for row in rows]
            for sid in ids:
                self.conn.execute(
                    """
                    UPDATE snapshots SET status = 'FAILED',
                    error = 'interrupted — recovered on startup'
                    WHERE snapshot_id = ?
                    """,
                    (sid,),
                )
            self.conn.commit()
        return ids

    def update_status(self, snapshot_id: str, status: SnapshotStatus) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE snapshots SET status = ? WHERE snapshot_id = ?",
                (status.value, snapshot_id),
            )
            self.conn.commit()

    def export_block_version(self, block_id: str, version: int) -> Optional[dict]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT block_id, version, data, deleted
                FROM block_versions WHERE block_id = ? AND version = ?
                """,
                (block_id, version),
            ).fetchone()
        return dict(row) if row else None

    def import_block_version(
        self,
        block_id: str,
        version: int,
        data: Optional[str],
        deleted: bool,
    ) -> str:
        return self.get_or_create_block_version(block_id, version, data, deleted)

    def _row_to_record(self, row: sqlite3.Row) -> SnapshotRecord:
        placements = json.loads(row["placements_json"] or "{}")
        return SnapshotRecord(
            snapshot_id=row["snapshot_id"],
            timestamp=row["timestamp"],
            block_count=row["block_count"],
            metadata_version=row["metadata_version"],
            status=SnapshotStatus(row["status"]),
            size_bytes=row["size_bytes"],
            placements=placements,
            error=row["error"],
        )

    # Policy storage
    def save_policy(self, policy) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_policies (
                    policy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    retention_count INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at INTEGER,
                    next_run_at INTEGER
                )
                """
            )
            self.conn.execute(
                """
                INSERT INTO snapshot_policies(
                    policy_id, name, schedule, retention_count, enabled,
                    last_run_at, next_run_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    name = excluded.name,
                    schedule = excluded.schedule,
                    retention_count = excluded.retention_count,
                    enabled = excluded.enabled,
                    last_run_at = excluded.last_run_at,
                    next_run_at = excluded.next_run_at
                """,
                (
                    policy.policy_id,
                    policy.name,
                    policy.schedule.value,
                    policy.retention_count,
                    int(policy.enabled),
                    policy.last_run_at,
                    policy.next_run_at,
                ),
            )
            self.conn.commit()

    def list_policies(self):
        from storage.models import PolicySchedule, SnapshotPolicy

        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_policies (
                    policy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    retention_count INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at INTEGER,
                    next_run_at INTEGER
                )
                """
            )
            rows = self.conn.execute(
                "SELECT * FROM snapshot_policies ORDER BY name"
            ).fetchall()
        return [
            SnapshotPolicy(
                policy_id=row["policy_id"],
                name=row["name"],
                schedule=PolicySchedule(row["schedule"]),
                retention_count=row["retention_count"],
                enabled=bool(row["enabled"]),
                last_run_at=row["last_run_at"],
                next_run_at=row["next_run_at"],
            )
            for row in rows
        ]

    # Backup metadata
    def _ensure_backup_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backups (
                backup_id TEXT PRIMARY KEY,
                backup_type TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
                block_count INTEGER NOT NULL DEFAULT 0,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'READY',
                archive_path TEXT,
                base_backup_id TEXT,
                error TEXT
            )
            """
        )

    def save_backup(self, backup) -> None:
        from storage.models import BackupRecord

        with self._lock:
            self._ensure_backup_table()
            self.conn.execute(
                """
                INSERT INTO backups(
                    backup_id, backup_type, timestamp, snapshot_ids_json,
                    block_count, size_bytes, status, archive_path,
                    base_backup_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(backup_id) DO UPDATE SET
                    status = excluded.status,
                    size_bytes = excluded.size_bytes,
                    block_count = excluded.block_count,
                    archive_path = excluded.archive_path,
                    error = excluded.error
                """,
                (
                    backup.backup_id,
                    backup.backup_type.value,
                    backup.timestamp,
                    json.dumps(backup.snapshot_ids),
                    backup.block_count,
                    backup.size_bytes,
                    backup.status.value,
                    backup.archive_path,
                    backup.base_backup_id,
                    backup.error,
                ),
            )
            self.conn.commit()

    def get_backup(self, backup_id: str):
        from storage.models import BackupRecord, BackupStatus, BackupType

        with self._lock:
            self._ensure_backup_table()
            row = self.conn.execute(
                "SELECT * FROM backups WHERE backup_id = ?",
                (backup_id,),
            ).fetchone()
        if not row:
            return None
        return BackupRecord(
            backup_id=row["backup_id"],
            backup_type=BackupType(row["backup_type"]),
            timestamp=row["timestamp"],
            snapshot_ids=json.loads(row["snapshot_ids_json"] or "[]"),
            block_count=row["block_count"],
            size_bytes=row["size_bytes"],
            status=BackupStatus(row["status"]),
            archive_path=row["archive_path"],
            base_backup_id=row["base_backup_id"],
            error=row["error"],
        )

    def list_backups(self):
        from storage.models import BackupRecord, BackupStatus, BackupType

        with self._lock:
            self._ensure_backup_table()
            rows = self.conn.execute(
                "SELECT * FROM backups ORDER BY timestamp DESC"
            ).fetchall()
        return [
            BackupRecord(
                backup_id=row["backup_id"],
                backup_type=BackupType(row["backup_type"]),
                timestamp=row["timestamp"],
                snapshot_ids=json.loads(row["snapshot_ids_json"] or "[]"),
                block_count=row["block_count"],
                size_bytes=row["size_bytes"],
                status=BackupStatus(row["status"]),
                archive_path=row["archive_path"],
                base_backup_id=row["base_backup_id"],
                error=row["error"],
            )
            for row in rows
        ]

    def save_restore_job(self, job) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS restore_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    blocks_restored INTEGER NOT NULL DEFAULT 0,
                    placements_restored INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    duration_ms REAL,
                    error TEXT
                )
                """
            )
            self.conn.execute(
                """
                INSERT INTO restore_jobs(
                    job_id, source_type, source_id, status,
                    blocks_restored, placements_restored,
                    created_at, completed_at, duration_ms, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    blocks_restored = excluded.blocks_restored,
                    placements_restored = excluded.placements_restored,
                    completed_at = excluded.completed_at,
                    duration_ms = excluded.duration_ms,
                    error = excluded.error
                """,
                (
                    job.job_id,
                    job.source_type,
                    job.source_id,
                    job.status.value,
                    job.blocks_restored,
                    job.placements_restored,
                    job.created_at,
                    job.completed_at,
                    job.duration_ms,
                    job.error,
                ),
            )
            self.conn.commit()

    def list_restore_jobs(self):
        from storage.models import RestoreJob, RestoreJobStatus

        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS restore_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    blocks_restored INTEGER NOT NULL DEFAULT 0,
                    placements_restored INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    duration_ms REAL,
                    error TEXT
                )
                """
            )
            rows = self.conn.execute(
                "SELECT * FROM restore_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [
            RestoreJob(
                job_id=row["job_id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                status=RestoreJobStatus(row["status"]),
                blocks_restored=row["blocks_restored"],
                placements_restored=row["placements_restored"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                duration_ms=row["duration_ms"],
                error=row["error"],
            )
            for row in rows
        ]
