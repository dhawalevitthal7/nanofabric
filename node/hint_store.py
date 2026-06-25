"""Durable store for hinted handoff entries."""

import json
import sqlite3
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def _now_ms() -> int:
    return int(time.time() * 1000)


class HintStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class Hint(BaseModel):
    hint_id: str
    target_node: str
    block_id: str
    version: int
    payload: str
    created_at: int = 0
    delivered_at: Optional[int] = None
    status: HintStatus = HintStatus.PENDING


class HintStore:

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS hints(
            hint_id TEXT PRIMARY KEY,
            target_node TEXT NOT NULL,
            block_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            delivered_at INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING'
        )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hints_status ON hints(status)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hints_target ON hints(target_node)"
        )
        self.conn.commit()

    def create_hint(
        self,
        target_node: str,
        block_id: str,
        version: int,
        payload: dict,
    ) -> Hint:
        now = _now_ms()
        hint_id = str(uuid.uuid4())
        payload_str = json.dumps(payload)
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO hints(
                    hint_id, target_node, block_id, version, payload,
                    created_at, delivered_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    hint_id,
                    target_node,
                    block_id,
                    version,
                    payload_str,
                    now,
                    HintStatus.PENDING.value,
                ),
            )
            self.conn.commit()
        return self.get_hint(hint_id)

    def get_hint(self, hint_id: str) -> Optional[Hint]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM hints WHERE hint_id = ?", (hint_id,)
            ).fetchone()
        return self._row_to_hint(row) if row else None

    def list_pending(self) -> List[Hint]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM hints WHERE status = ? ORDER BY created_at",
                (HintStatus.PENDING.value,),
            ).fetchall()
        return [self._row_to_hint(row) for row in rows]

    def list_all(self) -> List[Hint]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM hints ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_hint(row) for row in rows]

    def mark_delivered(self, hint_id: str) -> None:
        now = _now_ms()
        with self._lock:
            self.conn.execute(
                """
                UPDATE hints
                SET status = ?, delivered_at = ?
                WHERE hint_id = ?
                """,
                (HintStatus.DELIVERED.value, now, hint_id),
            )
            self.conn.commit()

    def mark_failed(self, hint_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE hints SET status = ? WHERE hint_id = ?",
                (HintStatus.FAILED.value, hint_id),
            )
            self.conn.commit()

    def delete_delivered(self) -> int:
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM hints WHERE status = ?",
                (HintStatus.DELIVERED.value,),
            )
            self.conn.commit()
            return cursor.rowcount

    def _row_to_hint(self, row) -> Hint:
        return Hint(
            hint_id=row["hint_id"],
            target_node=row["target_node"],
            block_id=row["block_id"],
            version=row["version"],
            payload=row["payload"],
            created_at=row["created_at"],
            delivered_at=row["delivered_at"],
            status=HintStatus(row["status"]),
        )

    def close(self):
        self.conn.close()
