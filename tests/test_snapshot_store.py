"""Tests for SnapshotStore."""

from storage.snapshot_store import SnapshotStore
from storage.models import SnapshotStatus


def test_create_and_get_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    record = store.create_snapshot_record(
        metadata_version=5,
        placements={"b1": ["node1", "node2"]},
    )
    assert record.status == SnapshotStatus.CREATING

    vid = store.get_or_create_block_version("b1", 1, "hello", False)
    store.add_snapshot_block(record.snapshot_id, "b1", vid)
    finalized = store.finalize_snapshot(
        record.snapshot_id, block_count=1, size_bytes=5
    )
    assert finalized.status == SnapshotStatus.READY
    assert finalized.block_count == 1

    loaded = store.get_snapshot(record.snapshot_id)
    assert loaded.placements == {"b1": ["node1", "node2"]}
    store.close()


def test_cow_block_version_reuse(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    vid1 = store.get_or_create_block_version("b1", 1, "data", False)
    vid2 = store.get_or_create_block_version("b1", 1, "data", False)
    assert vid1 == vid2

    row = store.conn.execute(
        "SELECT ref_count FROM block_versions WHERE version_id = ?", (vid1,)
    ).fetchone()
    assert row["ref_count"] == 2
    store.close()


def test_delete_snapshot_decrements_refs(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    record = store.create_snapshot_record(1, {})
    vid = store.get_or_create_block_version("b1", 1, "x", False)
    store.add_snapshot_block(record.snapshot_id, "b1", vid)
    store.finalize_snapshot(record.snapshot_id, 1, 1)

    deleted, size = store.delete_snapshot(record.snapshot_id)
    assert deleted is True
    assert size == 1

    count = store.conn.execute("SELECT COUNT(*) FROM block_versions").fetchone()[0]
    assert count == 0
    store.close()


def test_recover_interrupted_snapshots(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    record = store.create_snapshot_record(1, {})
    ids = store.recover_interrupted_snapshots()
    assert record.snapshot_id in ids
    snap = store.get_snapshot(record.snapshot_id)
    assert snap.status == SnapshotStatus.FAILED
    store.close()


def test_list_snapshots_ordered(tmp_path):
    import time

    store = SnapshotStore(tmp_path / "snapshots.db")
    r1 = store.create_snapshot_record(1, {})
    store.finalize_snapshot(r1.snapshot_id, 0, 0)
    time.sleep(0.01)
    r2 = store.create_snapshot_record(2, {})
    store.finalize_snapshot(r2.snapshot_id, 0, 0)

    snapshots = store.list_snapshots()
    assert snapshots[0].snapshot_id == r2.snapshot_id
    store.close()
