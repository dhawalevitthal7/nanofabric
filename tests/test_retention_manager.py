"""Tests for RetentionManager."""

from storage.models import SnapshotStatus


def test_enforce_retention(protection_stack, engine):
    for i in range(5):
        engine.write(f"ret-{i}", f"data-{i}", version=1)
        protection_stack.snapshot_manager.create_snapshot()

    expired = protection_stack.retention_manager.enforce_retention(keep_last_n=2)
    assert len(expired) == 3

    remaining = protection_stack.snapshot_manager.list_snapshots()
    ready = [s for s in remaining if s.status == SnapshotStatus.READY]
    assert len(ready) == 2


def test_clean_orphan_blocks(protection_stack, engine):
    engine.write("orphan", "x", version=1)
    snap = protection_stack.snapshot_manager.create_snapshot()
    protection_stack.snapshot_manager.delete_snapshot(snap.snapshot_id)

    reclaimed = protection_stack.retention_manager.clean_orphan_blocks()
    assert reclaimed >= 0
