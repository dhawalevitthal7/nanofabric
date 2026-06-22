import hashlib
import json
import logging
import os
import time
from pathlib import Path

from node.errors import OplogCorruptionError
from node.flush_worker import FlushWorker
from node.metrics import FsyncTimer, Metrics
from node.op_types import OpType

log = logging.getLogger(__name__)


def _payload_checksum(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _parse_record(line: str, line_no: int):
    record = json.loads(line)
    if "payload" in record and "checksum" in record:
        expected = _payload_checksum(record["payload"])
        if record["checksum"] != expected:
            raise OplogCorruptionError(
                line_no,
                f"checksum mismatch (expected {expected})",
            )
        return record["payload"]
    if "op" in record:
        return record
    raise OplogCorruptionError(line_no, "unrecognized entry format")


class Oplog:

    def __init__(
        self,
        path,
        node_id,
        metrics=None,
        fsync_policy="always",
        fsync_window_ms=10,
    ):
        self.path = Path(path)
        self.node_id = node_id
        self.metrics = metrics or Metrics()
        self.fsync_policy = fsync_policy
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._high_water_lsn = self._scan_high_water_mark()
        self._next_lsn = self._high_water_lsn + 1
        self._file = open(self.path, "a", buffering=1)
        self._pending_flush = False
        self._flush_worker = None

        if fsync_policy == "grouped":
            self._flush_worker = FlushWorker(
                self._do_fsync,
                window_ms=fsync_window_ms,
            )

    @property
    def high_water_lsn(self):
        return self._high_water_lsn

    def _scan_high_water_mark(self):
        max_lsn = 0
        if not self.path.exists():
            return max_lsn
        with open(self.path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _parse_record(line, line_no)
                    lsn = entry.get("lsn", 0)
                    if lsn > max_lsn:
                        max_lsn = lsn
                except (json.JSONDecodeError, OplogCorruptionError):
                    break
        return max_lsn

    def recover(self):
        """Truncate corrupt or partial tail after last valid entry."""
        if not self.path.exists():
            return 0

        last_good = 0
        with open(self.path, "r+b") as f:
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    break
                try:
                    stripped = line.decode("utf-8").strip()
                    if not stripped:
                        last_good = f.tell()
                        continue
                    _parse_record(stripped, 0)
                    last_good = f.tell()
                except (json.JSONDecodeError, OplogCorruptionError, UnicodeDecodeError):
                    log.warning(
                        "truncating oplog tail at offset %d",
                        pos,
                        extra={"node_id": self.node_id},
                    )
                    self.metrics.inc_corruption()
                    break
            f.truncate(last_good)

        self._high_water_lsn = self._scan_high_water_mark()
        self._next_lsn = self._high_water_lsn + 1
        return last_good

    def append(self, op, block_id, data=None, version=1, **extra):
        payload = {
            "lsn": self._next_lsn,
            "node_id": self.node_id,
            "ts_ms": int(time.time() * 1000),
            "op": op,
            "block_id": block_id,
            "version": version,
            **extra,
        }
        if data is not None:
            payload["data"] = data

        record = {
            "payload": payload,
            "checksum": _payload_checksum(payload),
        }
        line = json.dumps(record, separators=(",", ":")) + "\n"
        self._file.write(line)
        self._file.flush()
        self._pending_flush = True

        self._high_water_lsn = self._next_lsn
        self._next_lsn += 1

        if self.fsync_policy == "always":
            self._do_fsync()
        elif self._flush_worker:
            self._flush_worker.notify()

        return payload["lsn"]

    def _do_fsync(self):
        if not self._pending_flush:
            return
        with FsyncTimer(self.metrics):
            os.fsync(self._file.fileno())
        self._pending_flush = False

    def iter_entries(self):
        if not self.path.exists():
            return

        with open(self.path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield _parse_record(line, line_no)
                except json.JSONDecodeError as exc:
                    raise OplogCorruptionError(line_no, exc) from exc

    def compact(self, through_lsn):
        """Rewrite oplog keeping only entries with lsn > through_lsn."""
        if not self.path.exists():
            return 0

        kept = []
        for entry in self.iter_entries():
            lsn = entry.get("lsn", 0)
            if entry.get("op") == OpType.CHECKPOINT:
                continue
            if lsn > through_lsn:
                kept.append(entry)

        tmp = self.path.with_suffix(".compact.tmp")
        with open(tmp, "w", encoding="utf-8") as out:
            for payload in kept:
                record = {
                    "payload": payload,
                    "checksum": _payload_checksum(payload),
                }
                out.write(json.dumps(record, separators=(",", ":")) + "\n")
            out.flush()
            os.fsync(out.fileno())

        self.close()
        tmp.replace(self.path)
        self._file = open(self.path, "a", buffering=1)
        self._high_water_lsn = self._scan_high_water_mark()
        self._next_lsn = self._high_water_lsn + 1
        return len(kept)

    def close(self):
        if self._flush_worker:
            self._flush_worker.stop()
            self._flush_worker = None
        if self.fsync_policy == "grouped":
            self._do_fsync()
        if self._file and not self._file.closed:
            self._file.close()
