"""Tests for SQLite metadata persistence."""

from metadata.metadata_store import MetadataStore


def test_save_and_load_placement(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)

    store.save_placement("invoice-1", version=1, nodes=["node1", "node2"])
    store.save_placement("invoice-2", version=1, nodes=["node2"])

    assert store.get_block_locations("invoice-1") == ["node1", "node2"]
    assert store.get_block_locations("invoice-2") == ["node2"]
    assert store.block_exists("invoice-1")
    assert not store.block_exists("missing")

    store.close()

    store2 = MetadataStore(db_path)
    placements, versions, block_count = store2.load_recovery_snapshot()

    assert placements == {
        "invoice-1": ["node1", "node2"],
        "invoice-2": ["node2"],
    }
    assert versions == {"invoice-1": 1, "invoice-2": 1}
    assert block_count == 2
    assert store2.get_stats() == {"total_blocks": 2, "total_placements": 3}
    store2.close()


def test_delete_block(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    store.save_placement("invoice-1", version=1, nodes=["node1"])

    assert store.delete_block("invoice-1") is True
    assert store.get_block_locations("invoice-1") is None
    assert store.delete_block("invoice-1") is False
    store.close()


def test_node_stats_persistence(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_node("node1", status="UP", last_seen=1000)
    store.update_node_stats("node1", block_count=10, used_bytes=1024, last_lsn=42)

    store.close()
    store2 = MetadataStore(db_path)
    row = store2._conn.execute(
        "SELECT block_count, used_bytes, last_lsn FROM nodes WHERE node_id = ?",
        ("node1",),
    ).fetchone()
    assert row["block_count"] == 10
    assert row["used_bytes"] == 1024
    assert row["last_lsn"] == 42
    store2.close()


def test_get_node_blocks(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    store.save_placement("invoice-1", version=1, nodes=["node1", "node2"])
    store.save_placement("invoice-2", version=1, nodes=["node2"])

    assert store.get_node_blocks("node1") == ["invoice-1"]
    assert store.get_node_blocks("node2") == ["invoice-1", "invoice-2"]
    store.close()
