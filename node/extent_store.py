import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from node.errors import DataCorruptionError


def _checksum(data):
    if data is None:
        return ""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class ExtentStore:

    REPLAY_CURSOR_KEY = "replay_lsn"

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.create_table()

    def create_table(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS blocks(
            block_id TEXT PRIMARY KEY,
            data TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            data_checksum TEXT NOT NULL DEFAULT '',
            data_len INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at_ms INTEGER,
            origin_node_id TEXT,
            updated_at_ms INTEGER,
            origin_lsn INTEGER
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS node_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        self.conn.commit()
        self._migrate_schema()

    def _migrate_schema(self):
        columns = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(blocks)")
        }
        additions = {
            "version": "INTEGER NOT NULL DEFAULT 1",
            "data_checksum": "TEXT NOT NULL DEFAULT ''",
            "data_len": "INTEGER NOT NULL DEFAULT 0",
            "deleted": "INTEGER NOT NULL DEFAULT 0",
            "deleted_at_ms": "INTEGER",
            "origin_node_id": "TEXT",
            "updated_at_ms": "INTEGER",
            "origin_lsn": "INTEGER",
        }
        for col, typedef in additions.items():
            if col not in columns:
                self.conn.execute(
                    f"ALTER TABLE blocks ADD COLUMN {col} {typedef}"
                )
        self.conn.commit()

    @contextmanager
    def transaction(self):
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_replay_cursor(self):
        row = self.conn.execute(
            "SELECT value FROM node_meta WHERE key=?",
            (self.REPLAY_CURSOR_KEY,),
        ).fetchone()
        return int(row["value"]) if row else 0

    def set_replay_cursor(self, lsn, commit=True):
        self.conn.execute(
            """
            INSERT INTO node_meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (self.REPLAY_CURSOR_KEY, str(lsn)),
        )
        if commit:
            self.conn.commit()

    def save_if_newer(
        self,
        block_id,
        data,
        version,
        origin_node_id=None,
        origin_lsn=None,
        updated_at_ms=None,
    ):
        checksum = _checksum(data)
        data_len = len(data.encode("utf-8")) if data else 0
        ts = updated_at_ms or int(time.time() * 1000)

        self.conn.execute(
            """
            INSERT INTO blocks(
                block_id, data, version, data_checksum, data_len,
                deleted, deleted_at_ms, origin_node_id, updated_at_ms, origin_lsn
            ) VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?, ?)
            ON CONFLICT(block_id) DO UPDATE SET
                data = excluded.data,
                version = excluded.version,
                data_checksum = excluded.data_checksum,
                data_len = excluded.data_len,
                deleted = 0,
                deleted_at_ms = NULL,
                origin_node_id = excluded.origin_node_id,
                updated_at_ms = excluded.updated_at_ms,
                origin_lsn = excluded.origin_lsn
            WHERE excluded.version > blocks.version
            """,
            (
                block_id,
                data,
                version,
                checksum,
                data_len,
                origin_node_id,
                ts,
                origin_lsn,
            ),
        )

    def tombstone_if_newer(
        self,
        block_id,
        version,
        origin_node_id=None,
        origin_lsn=None,
        deleted_at_ms=None,
    ):
        ts = deleted_at_ms or int(time.time() * 1000)
        self.conn.execute(
            """
            INSERT INTO blocks(
                block_id, data, version, data_checksum, data_len,
                deleted, deleted_at_ms, origin_node_id, updated_at_ms, origin_lsn
            ) VALUES (?, NULL, ?, '', 0, 1, ?, ?, ?, ?)
            ON CONFLICT(block_id) DO UPDATE SET
                data = NULL,
                version = excluded.version,
                data_checksum = '',
                data_len = 0,
                deleted = 1,
                deleted_at_ms = excluded.deleted_at_ms,
                origin_node_id = excluded.origin_node_id,
                updated_at_ms = excluded.updated_at_ms,
                origin_lsn = excluded.origin_lsn
            WHERE excluded.version > blocks.version
               OR (excluded.version = blocks.version AND blocks.deleted = 0)
            """,
            (
                block_id,
                version,
                ts,
                origin_node_id,
                ts,
                origin_lsn,
            ),
        )

    def get_row(self, block_id):
        row = self.conn.execute(
            """
            SELECT block_id, data, version, deleted, data_checksum,
                   data_len, origin_node_id, updated_at_ms, origin_lsn
            FROM blocks WHERE block_id=?
            """,
            (block_id,),
        ).fetchone()
        if not row:
            return None
        record = dict(row)
        if record["deleted"]:
            return record
        if record["data"] is not None:
            actual = _checksum(record["data"])
            if record["data_checksum"] and actual != record["data_checksum"]:
                raise DataCorruptionError(block_id)
        return record

    def get(self, block_id):
        row = self.get_row(block_id)
        if not row or row["deleted"]:
            return None
        return row["data"]

    def list_blocks(self):
        rows = self.conn.execute(
            "SELECT block_id FROM blocks WHERE deleted=0 ORDER BY block_id"
        ).fetchall()
        return [row["block_id"] for row in rows]

    def count_blocks(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM blocks WHERE deleted=0"
        ).fetchone()
        return row["cnt"]

    def close(self):
        self.conn.close()
