"""SQLite-backed durable Raft state."""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from metadata.raft.models import CommandType, LogEntry

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raft_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_term INTEGER NOT NULL DEFAULT 0,
    voted_for TEXT
);

CREATE TABLE IF NOT EXISTS raft_log (
    log_index INTEGER PRIMARY KEY,
    term INTEGER NOT NULL,
    command TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS raft_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_included_index INTEGER NOT NULL DEFAULT 0,
    last_included_term INTEGER NOT NULL DEFAULT 0,
    data TEXT NOT NULL DEFAULT '{}'
);
"""


class RaftStorage:
    """Persists Raft persistent state to raft.db."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT id FROM raft_state WHERE id = 1").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO raft_state (id, current_term, voted_for) VALUES (1, 0, NULL)"
                )
            snap = self._conn.execute("SELECT id FROM raft_snapshot WHERE id = 1").fetchone()
            if snap is None:
                self._conn.execute(
                    """
                    INSERT INTO raft_snapshot
                        (id, last_included_index, last_included_term, data)
                    VALUES (1, 0, 0, '{}')
                    """
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_state(self) -> Tuple[int, Optional[str]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT current_term, voted_for FROM raft_state WHERE id = 1"
            ).fetchone()
            return row["current_term"], row["voted_for"]

    def set_state(self, current_term: int, voted_for: Optional[str]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE raft_state SET current_term = ?, voted_for = ? WHERE id = 1",
                (current_term, voted_for),
            )
            self._conn.commit()

    def get_log(self) -> List[LogEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT log_index, term, command, payload FROM raft_log ORDER BY log_index"
            ).fetchall()
            return [
                LogEntry(
                    index=row["log_index"],
                    term=row["term"],
                    command=CommandType(row["command"]),
                    payload=json.loads(row["payload"]),
                )
                for row in rows
            ]

    def append_entries(self, entries: List[LogEntry]) -> None:
        if not entries:
            return
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO raft_log (log_index, term, command, payload)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (e.index, e.term, e.command.value, json.dumps(e.payload))
                    for e in entries
                ],
            )
            self._conn.commit()

    def truncate_log_from(self, start_index: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM raft_log WHERE log_index >= ?",
                (start_index,),
            )
            self._conn.commit()

    def get_snapshot(self) -> Tuple[int, int, dict]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT last_included_index, last_included_term, data
                FROM raft_snapshot WHERE id = 1
                """
            ).fetchone()
            return (
                row["last_included_index"],
                row["last_included_term"],
                json.loads(row["data"]),
            )

    def save_snapshot(self, last_index: int, last_term: int, data: dict) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE raft_snapshot
                SET last_included_index = ?, last_included_term = ?, data = ?
                WHERE id = 1
                """,
                (last_index, last_term, json.dumps(data)),
            )
            self._conn.execute(
                "DELETE FROM raft_log WHERE log_index <= ?",
                (last_index,),
            )
            self._conn.commit()
        log.info(
            "raft snapshot saved",
            extra={"last_index": last_index, "last_term": last_term},
        )
