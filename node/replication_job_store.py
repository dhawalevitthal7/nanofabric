"""Durable store for replication jobs — survives node restarts."""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

from node.replication_models import JobStatus, ReplicationJob


def _now_ms() -> int:
    return int(time.time() * 1000)


class ReplicationJobStore:

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS replication_jobs(
            job_id TEXT PRIMARY KEY,
            block_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            primary_node TEXT NOT NULL,
            target_node TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            is_delete INTEGER NOT NULL DEFAULT 0,
            data TEXT,
            lsn INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON replication_jobs(status)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_block ON replication_jobs(block_id)"
        )
        self.conn.commit()

    def create_job(
        self,
        block_id: str,
        version: int,
        primary_node: str,
        target_node: str,
        lsn: int,
        data: Optional[str] = None,
        is_delete: bool = False,
    ) -> ReplicationJob:
        now = _now_ms()
        job_id = str(uuid.uuid4())
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO replication_jobs(
                    job_id, block_id, version, primary_node, target_node,
                    status, attempt_count, last_error, is_delete, data, lsn,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    block_id,
                    version,
                    primary_node,
                    target_node,
                    JobStatus.PENDING.value,
                    1 if is_delete else 0,
                    data,
                    lsn,
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[ReplicationJob]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM replication_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        last_error: Optional[str] = None,
        increment_attempt: bool = False,
    ) -> None:
        now = _now_ms()
        with self._lock:
            if increment_attempt:
                self.conn.execute(
                    """
                    UPDATE replication_jobs
                    SET status = ?, last_error = ?, attempt_count = attempt_count + 1,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (status.value, last_error, now, job_id),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE replication_jobs
                    SET status = ?, last_error = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (status.value, last_error, now, job_id),
                )
            self.conn.commit()

    def list_jobs_by_status(self, status: JobStatus) -> List[ReplicationJob]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM replication_jobs WHERE status = ? ORDER BY created_at",
                (status.value,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_pending_and_failed(self) -> List[ReplicationJob]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM replication_jobs
                WHERE status IN (?, ?)
                ORDER BY created_at
                """,
                (JobStatus.PENDING.value, JobStatus.FAILED.value),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_all_jobs(self) -> List[ReplicationJob]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM replication_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def delete_completed_jobs(self, block_id: str, version: int) -> None:
        with self._lock:
            self.conn.execute(
                """
                DELETE FROM replication_jobs
                WHERE block_id = ? AND version = ? AND status = ?
                """,
                (block_id, version, JobStatus.SUCCESS.value),
            )
            self.conn.commit()

    def _row_to_job(self, row) -> ReplicationJob:
        return ReplicationJob(
            job_id=row["job_id"],
            block_id=row["block_id"],
            version=row["version"],
            primary_node=row["primary_node"],
            target_node=row["target_node"],
            status=JobStatus(row["status"]),
            attempt_count=row["attempt_count"],
            last_error=row["last_error"],
            is_delete=bool(row["is_delete"]),
            data=row["data"],
            lsn=row["lsn"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self):
        self.conn.close()
