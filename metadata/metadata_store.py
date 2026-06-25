"""SQLite-backed durable metadata store for placements and node state."""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'UP',
    last_seen INTEGER NOT NULL DEFAULT 0,
    block_count INTEGER NOT NULL DEFAULT 0,
    used_bytes INTEGER NOT NULL DEFAULT 0,
    last_lsn INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks (
    block_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS placements (
    block_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    PRIMARY KEY (block_id, node_id),
    FOREIGN KEY (block_id) REFERENCES blocks(block_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_placements_node ON placements(node_id);
"""


def _now_ms() -> int:
    return int(time.time() * 1000)


class MetadataStore:
    """Persists block placements and node statistics with atomic writes."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert_node(
        self,
        node_id: str,
        status: str = "UP",
        last_seen: Optional[int] = None,
        block_count: Optional[int] = None,
        used_bytes: Optional[int] = None,
        last_lsn: Optional[int] = None,
    ) -> None:
        now = last_seen if last_seen is not None else _now_ms()
        with self._lock:
            existing = self._conn.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()

            if existing:
                updates = ["status = ?", "last_seen = ?"]
                params: list = [status, now]
                if block_count is not None:
                    updates.append("block_count = ?")
                    params.append(block_count)
                if used_bytes is not None:
                    updates.append("used_bytes = ?")
                    params.append(used_bytes)
                if last_lsn is not None:
                    updates.append("last_lsn = ?")
                    params.append(last_lsn)
                params.append(node_id)
                self._conn.execute(
                    f"UPDATE nodes SET {', '.join(updates)} WHERE node_id = ?",
                    params,
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO nodes
                        (node_id, status, last_seen, block_count, used_bytes, last_lsn)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        status,
                        now,
                        block_count if block_count is not None else 0,
                        used_bytes if used_bytes is not None else 0,
                        last_lsn if last_lsn is not None else 0,
                    ),
                )
            self._conn.commit()

    def update_node_stats(
        self,
        node_id: str,
        block_count: int,
        used_bytes: int,
        last_lsn: int,
        last_seen: Optional[int] = None,
    ) -> None:
        self.upsert_node(
            node_id=node_id,
            last_seen=last_seen,
            block_count=block_count,
            used_bytes=used_bytes,
            last_lsn=last_lsn,
        )

    def save_placement(
        self,
        block_id: str,
        version: int,
        nodes: List[str],
    ) -> None:
        created_at = _now_ms()
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    INSERT INTO blocks (block_id, version, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(block_id) DO UPDATE SET version = excluded.version
                    """,
                    (block_id, version, created_at),
                )
                self._conn.execute(
                    "DELETE FROM placements WHERE block_id = ?",
                    (block_id,),
                )
                self._conn.executemany(
                    "INSERT INTO placements (block_id, node_id) VALUES (?, ?)",
                    [(block_id, node_id) for node_id in nodes],
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def delete_block(self, block_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM blocks WHERE block_id = ?",
                (block_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def get_block_locations(self, block_id: str) -> Optional[List[str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT node_id FROM placements WHERE block_id = ? ORDER BY node_id",
                (block_id,),
            ).fetchall()
            return [row["node_id"] for row in rows] if rows else None

    def block_exists(self, block_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM blocks WHERE block_id = ?",
                (block_id,),
            ).fetchone()
            return row is not None

    def list_all_placements(self) -> Dict[str, List[str]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT block_id, node_id
                FROM placements
                ORDER BY block_id, node_id
                """
            ).fetchall()
            result: Dict[str, List[str]] = {}
            for row in rows:
                result.setdefault(row["block_id"], []).append(row["node_id"])
            return result

    def get_node_blocks(self, node_id: str) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT block_id FROM placements WHERE node_id = ? ORDER BY block_id",
                (node_id,),
            ).fetchall()
            return [row["block_id"] for row in rows]

    def load_recovery_snapshot(
        self,
    ) -> Tuple[Dict[str, List[str]], Dict[str, int], int]:
        """Return (placements, versions, block_count) for startup recovery."""
        with self._lock:
            placement_rows = self._conn.execute(
                """
                SELECT p.block_id, p.node_id
                FROM placements p
                ORDER BY p.block_id, p.node_id
                """
            ).fetchall()
            placements: Dict[str, List[str]] = {}
            for row in placement_rows:
                placements.setdefault(row["block_id"], []).append(row["node_id"])

            version_rows = self._conn.execute(
                "SELECT block_id, version FROM blocks ORDER BY created_at, block_id"
            ).fetchall()
            versions = {row["block_id"]: row["version"] for row in version_rows}

            block_count = self._conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
            return placements, versions, block_count

    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            total_blocks = self._conn.execute(
                "SELECT COUNT(*) FROM blocks"
            ).fetchone()[0]
            total_placements = self._conn.execute(
                "SELECT COUNT(*) FROM placements"
            ).fetchone()[0]
            return {
                "total_blocks": total_blocks,
                "total_placements": total_placements,
            }
