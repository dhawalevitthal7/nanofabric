"""Durable SQLite store for repair jobs — survives crashes and restarts."""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

from cluster.repair_models import RepairJob, RepairStatus, RepairType


def _now_ms() -> int:
    return int(time.time() * 1000)


class RepairJobStore:

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS repair_jobs(
            job_id TEXT PRIMARY KEY,
            block_id TEXT NOT NULL,
            source_node TEXT NOT NULL,
            target_node TEXT NOT NULL,
            version INTEGER NOT NULL,
            repair_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            completed_at INTEGER
        )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repair_status ON repair_jobs(status)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repair_block ON repair_jobs(block_id)"
        )
        self.conn.commit()

    def create_job(
        self,
        block_id: str,
        source_node: str,
        target_node: str,
        version: int,
        repair_type: RepairType,
    ) -> RepairJob:
        existing = self.find_active_job(block_id, target_node, repair_type)
        if existing:
            return existing

        now = _now_ms()
        job_id = str(uuid.uuid4())
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO repair_jobs(
                    job_id, block_id, source_node, target_node, version,
                    repair_type, status, attempt_count, last_error,
                    created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, NULL)
                """,
                (
                    job_id,
                    block_id,
                    source_node,
                    target_node,
                    version,
                    repair_type.value,
                    RepairStatus.PENDING.value,
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return self.get_job(job_id)

    def find_active_job(
        self,
        block_id: str,
        target_node: str,
        repair_type: RepairType,
    ) -> Optional[RepairJob]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT * FROM repair_jobs
                WHERE block_id = ? AND target_node = ? AND repair_type = ?
                  AND status IN (?, ?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    block_id,
                    target_node,
                    repair_type.value,
                    RepairStatus.PENDING.value,
                    RepairStatus.COPYING.value,
                    RepairStatus.VERIFYING.value,
                ),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def get_job(self, job_id: str) -> Optional[RepairJob]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM repair_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def update_job_status(
        self,
        job_id: str,
        status: RepairStatus,
        last_error: Optional[str] = None,
        increment_attempt: bool = False,
    ) -> None:
        now = _now_ms()
        completed_at = now if status == RepairStatus.COMPLETED else None
        with self._lock:
            if increment_attempt:
                if completed_at is not None:
                    self.conn.execute(
                        """
                        UPDATE repair_jobs
                        SET status = ?, last_error = ?, attempt_count = attempt_count + 1,
                            updated_at = ?, completed_at = ?
                        WHERE job_id = ?
                        """,
                        (status.value, last_error, now, completed_at, job_id),
                    )
                else:
                    self.conn.execute(
                        """
                        UPDATE repair_jobs
                        SET status = ?, last_error = ?, attempt_count = attempt_count + 1,
                            updated_at = ?
                        WHERE job_id = ?
                        """,
                        (status.value, last_error, now, job_id),
                    )
            else:
                if completed_at is not None:
                    self.conn.execute(
                        """
                        UPDATE repair_jobs
                        SET status = ?, last_error = ?, updated_at = ?, completed_at = ?
                        WHERE job_id = ?
                        """,
                        (status.value, last_error, now, completed_at, job_id),
                    )
                else:
                    self.conn.execute(
                        """
                        UPDATE repair_jobs
                        SET status = ?, last_error = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (status.value, last_error, now, job_id),
                    )
            self.conn.commit()

    def list_jobs_by_status(self, status: RepairStatus) -> List[RepairJob]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM repair_jobs WHERE status = ? ORDER BY created_at",
                (status.value,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_pending_and_failed(self) -> List[RepairJob]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM repair_jobs
                WHERE status IN (?, ?, ?, ?)
                ORDER BY created_at
                """,
                (
                    RepairStatus.PENDING.value,
                    RepairStatus.COPYING.value,
                    RepairStatus.VERIFYING.value,
                    RepairStatus.FAILED.value,
                ),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_interrupted_jobs(self) -> List[RepairJob]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM repair_jobs
                WHERE status IN (?, ?)
                ORDER BY created_at
                """,
                (RepairStatus.COPYING.value, RepairStatus.VERIFYING.value),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_all_jobs(self) -> List[RepairJob]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM repair_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def _row_to_job(self, row) -> RepairJob:
        return RepairJob(
            job_id=row["job_id"],
            block_id=row["block_id"],
            source_node=row["source_node"],
            target_node=row["target_node"],
            version=row["version"],
            repair_type=RepairType(row["repair_type"]),
            status=RepairStatus(row["status"]),
            attempt_count=row["attempt_count"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    def close(self) -> None:
        self.conn.close()
