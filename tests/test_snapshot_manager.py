"""Tests for SnapshotManager."""

from storage.models import SnapshotStatus


def test_create_snapshot_captures_blocks(protection_stack, engine, metadata_store):
    engine.write("block-a", "alpha", version=1)
    engine.write("block-b", "beta", version=1)
    metadata_store.save_placement("block-a", 1, ["node1"])
    metadata_store.save_placement("block-b", 1, ["node1"])

    snapshot = protection_stack.snapshot_manager.create_snapshot()
    assert snapshot.status == SnapshotStatus.READY
    assert snapshot.block_count == 2
    assert snapshot.metadata_version == 2

    blocks = protection_stack.snapshot_manager.get_snapshot_blocks(snapshot.snapshot_id)
    assert len(blocks) == 2
    data = {b["block_id"]: b["data"] for b in blocks}
    assert data["block-a"] == "alpha"
    assert data["block-b"] == "beta"


def test_list_and_delete_snapshot(protection_stack, engine):
    engine.write("x", "data", version=1)
    snap = protection_stack.snapshot_manager.create_snapshot()
    listed = protection_stack.snapshot_manager.list_snapshots()
    assert any(s.snapshot_id == snap.snapshot_id for s in listed)

    assert protection_stack.snapshot_manager.delete_snapshot(snap.snapshot_id)
    assert protection_stack.snapshot_manager.get_snapshot(snap.snapshot_id) is None


def test_snapshot_preserves_placements(protection_stack, engine, metadata_store):
    engine.write("p1", "v", version=1)
    metadata_store.save_placement("p1", 1, ["node1", "node2"])

    snap = protection_stack.snapshot_manager.create_snapshot()
    assert snap.placements == {"p1": ["node1", "node2"]}
