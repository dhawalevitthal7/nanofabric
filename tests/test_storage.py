import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import threading

import pytest

from node.errors import ValidationError, VersionConflictError
from node.storage_engine import StorageEngine


def test_write_and_read(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("invoice-1", "jay data")
        assert engine.read("invoice-1") == "jay data"


def test_durability(tmp_path):
    data_dir = tmp_path / "node1"
    with StorageEngine(str(data_dir), node_id="node1") as engine:
        for i in range(100):
            engine.write(f"block-{i}", f"value-{i}")

    with StorageEngine(str(data_dir), node_id="node1") as engine2:
        for i in range(100):
            assert engine2.read(f"block-{i}") == f"value-{i}"


def test_list_blocks(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("a", "1")
        engine.write("b", "2")
        assert sorted(engine.list_blocks()) == ["a", "b"]


def test_delete(tmp_path):
    data_dir = tmp_path / "node1"
    with StorageEngine(str(data_dir), node_id="node1") as engine:
        engine.write("temp", "data")
        assert engine.read("temp") == "data"
        engine.delete("temp")
        assert engine.read("temp") is None

    with StorageEngine(str(data_dir), node_id="node1") as engine2:
        assert engine2.read("temp") is None


def test_read_block_metadata(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("meta-block", "payload")
        record = engine.read_block("meta-block")
        assert record.block_id == "meta-block"
        assert record.data == "payload"
        assert record.version == 1
        assert record.deleted is False
        assert record.origin_node_id == "node1"
        assert record.origin_lsn == 1


def test_version_conflict_rejected(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("vblock", "v1", version=1)
        engine.write("vblock", "v2", version=2)
        with pytest.raises(VersionConflictError):
            engine.write("vblock", "stale", version=2)


def test_auto_version_increment(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("auto", "first")
        engine.write("auto", "second")
        record = engine.read_block("auto")
        assert record.data == "second"
        assert record.version == 2


def test_invalid_block_id_rejected(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        with pytest.raises(ValidationError):
            engine.write("", "data")


def test_get_stats(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("s1", "data")
        stats = engine.get_stats()
        assert stats["node_id"] == "node1"
        assert stats["block_count"] == 1
        assert stats["last_lsn"] >= 1
        assert stats["writes_total"] == 1


def test_checkpoint_and_manifest(tmp_path):
    data_dir = tmp_path / "node1"
    with StorageEngine(str(data_dir), node_id="node1") as engine:
        engine.write("ck", "data")
        lsn = engine.checkpoint()
        assert lsn >= 1
        stats = engine.get_stats()
        assert stats["last_checkpoint_lsn"] == lsn

    manifest_path = data_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["node_id"] == "node1"
    assert manifest["block_count"] == 1


def test_concurrent_read_write(tmp_path):
    with StorageEngine(str(tmp_path / "node1"), node_id="node1") as engine:
        engine.write("shared", "start")
        errors = []

        def writer():
            try:
                for i in range(50):
                    engine.write("shared", f"v{i}")
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                for _ in range(50):
                    engine.read("shared")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert engine.read("shared") is not None
