"""Tests for RestoreService."""

from storage.models import RestoreJobStatus


def test_restore_snapshot_reverts_data(protection_stack, engine, metadata_store):
    engine.write_local("r1", "original", version=1)
    metadata_store.save_placement("r1", 1, ["node1"])
    snap = protection_stack.snapshot_manager.create_snapshot()

    engine.write_local("r1", "modified", version=2)
    assert engine.read("r1") == "modified"

    job = protection_stack.restore_service.restore_snapshot(snap.snapshot_id)
    assert job.status == RestoreJobStatus.COMPLETED
    assert job.blocks_restored >= 1
    assert engine.read("r1") == "original"


def test_restore_after_delete(protection_stack, engine, metadata_store):
    engine.write("del-me", "keep", version=1)
    metadata_store.save_placement("del-me", 1, ["node1"])
    snap = protection_stack.snapshot_manager.create_snapshot()

    engine.delete_local("del-me", version=2, allow_idempotent=True)
    assert engine.read("del-me") is None

    job = protection_stack.restore_service.restore_snapshot(snap.snapshot_id)
    assert job.status == RestoreJobStatus.COMPLETED
    assert engine.read("del-me") == "keep"


def test_restore_missing_snapshot(protection_stack):
    job = protection_stack.restore_service.restore_snapshot("nonexistent")
    assert job.status == RestoreJobStatus.FAILED
