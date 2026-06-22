import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

import pytest

from node.errors import OplogCorruptionError
from node.oplog import Oplog
from node.storage_engine import StorageEngine


def _write_legacy_entry(path, entry):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def test_truncated_oplog_tail_recovery(tmp_path):
    data_dir = tmp_path / "node1"
    data_dir.mkdir()
    oplog_path = data_dir / "oplog.jsonl"

    oplog = Oplog(oplog_path, node_id="node1")
    oplog.append("write", "good", data="ok", version=1)
    oplog.close()

    with open(oplog_path, "ab") as f:
        f.write(b'{"payload": {"op": "write", "trunc')

    engine = StorageEngine(str(data_dir), node_id="node1")
    assert engine.read("good") == "ok"
    engine.close()


def test_replay_idempotent(tmp_path):
    data_dir = tmp_path / "node1"
    with StorageEngine(str(data_dir), node_id="node1") as engine:
        engine.write("idem", "value")

    engine2 = StorageEngine(str(data_dir), node_id="node1")
    engine2._replay_oplog()
    assert engine2.read("idem") == "value"
    engine2.close()


def test_legacy_oplog_format_replay(tmp_path):
    data_dir = tmp_path / "node1"
    data_dir.mkdir()
    oplog_path = data_dir / "oplog.jsonl"
    _write_legacy_entry(
        oplog_path,
        {
            "op": "write",
            "block_id": "legacy",
            "data": "old-format",
            "version": 1,
        },
    )

    with StorageEngine(str(data_dir), node_id="node1") as engine:
        assert engine.read("legacy") == "old-format"


def test_oplog_checksum_verification(tmp_path):
    data_dir = tmp_path / "node1"
    oplog = Oplog(data_dir / "oplog.jsonl", node_id="node1")
    oplog.append("write", "chk", data="data", version=1)
    oplog.close()

    lines = (data_dir / "oplog.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["checksum"] = "bad"
    (data_dir / "oplog.jsonl").write_text(
        json.dumps(record) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(OplogCorruptionError):
        list(Oplog(data_dir / "oplog.jsonl", node_id="node1").iter_entries())


def test_delete_tombstone_survives_restart(tmp_path):
    data_dir = tmp_path / "node1"
    with StorageEngine(str(data_dir), node_id="node1") as engine:
        engine.write("gone", "data")
        engine.delete("gone")

    with StorageEngine(str(data_dir), node_id="node1") as engine2:
        assert engine2.read("gone") is None
        assert "gone" not in engine2.list_blocks()
        row = engine2.db.get_row("gone")
        assert row is not None
        assert row["deleted"] == 1
