"""End-to-end disaster recovery scenario tests."""

from pathlib import Path

from node.storage_engine import StorageEngine
from metadata.metadata_store import MetadataStore
from storage.cluster_bridge import EngineBlockAdapter, make_placement_restore
from storage.models import BackupType, RestoreJobStatus
from storage.protection_factory import build_protection_stack


def _build_stack(data_dir, engine, store):
    adapter = EngineBlockAdapter(engine)

    def clear_blocks():
        engine.purge_all_blocks()

    return build_protection_stack(
        data_dir=data_dir,
        read_blocks=adapter,
        write_blocks=adapter,
        get_metadata_version=lambda: store.get_stats()["total_blocks"],
        get_placements=store.list_all_placements,
        restore_placement=make_placement_restore(store),
        clear_blocks=clear_blocks,
    )


def test_full_disaster_recovery_workflow(tmp_path):
    """Phase 9 demo: create, snapshot, modify, delete, restore, backup, new cluster."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"

    source_engine = StorageEngine(source_dir / "node", node_id="node1")
    source_store = MetadataStore(source_dir / "metadata.db")
    source_stack = _build_stack(source_dir / "protection", source_engine, source_store)

    source_engine.write("demo-block", "initial-data", version=1)
    source_engine.write("demo-block-2", "more-data", version=1)
    source_store.save_placement("demo-block", 1, ["node1", "node2"])
    source_store.save_placement("demo-block-2", 1, ["node1"])

    snapshot = source_stack.snapshot_manager.create_snapshot()
    assert snapshot.block_count == 2

    source_engine.write("demo-block", "modified-data", version=2)
    source_engine.delete_local("demo-block-2", version=2, allow_idempotent=True)
    assert source_engine.read("demo-block") == "modified-data"
    assert source_engine.read("demo-block-2") is None

    restore_job = source_stack.restore_service.restore_snapshot(snapshot.snapshot_id)
    assert restore_job.status == RestoreJobStatus.COMPLETED
    assert source_engine.read("demo-block") == "initial-data"
    assert source_engine.read("demo-block-2") == "more-data"

    backup = source_stack.backup_service.create_backup(BackupType.FULL)
    assert backup.archive_path
    assert Path(backup.archive_path).exists()

    source_stack.close()
    source_engine.close()
    source_store.close()

    target_engine = StorageEngine(target_dir / "node", node_id="node1")
    target_store = MetadataStore(target_dir / "metadata.db")
    target_stack = _build_stack(target_dir / "protection", target_engine, target_store)

    imported = target_stack.backup_service.import_backup(backup.archive_path)
    restore_job = target_stack.restore_service.restore_backup(
        imported.backup_id, target_stack.backup_service
    )
    assert restore_job.status == RestoreJobStatus.COMPLETED
    assert target_engine.read("demo-block") == "initial-data"
    assert target_engine.read("demo-block-2") == "more-data"
    assert target_store.get_block_locations("demo-block") == ["node1", "node2"]

    target_stack.close()
    target_engine.close()
    target_store.close()


def test_interrupted_snapshot_recovery(tmp_path):
    store_path = tmp_path / "protection"
    engine = StorageEngine(tmp_path / "node", node_id="node1")
    meta = MetadataStore(tmp_path / "metadata.db")
    stack = _build_stack(store_path, engine, meta)

    record = stack.store.create_snapshot_record(0, {})
    assert record.snapshot_id
    stack.close()

    stack2 = _build_stack(store_path, engine, meta)
    snap = stack2.store.get_snapshot(record.snapshot_id)
    assert snap is not None
    assert snap.status.value == "FAILED"

    stack2.close()
    engine.close()
    meta.close()


def test_partial_backup_corruption_detected(tmp_path):
    import json
    import zipfile

    engine = StorageEngine(tmp_path / "node", node_id="node1")
    meta = MetadataStore(tmp_path / "metadata.db")
    stack = _build_stack(tmp_path / "protection", engine, meta)

    engine.write("c1", "checksum-test", version=1)
    meta.save_placement("c1", 1, ["node1"])
    backup = stack.backup_service.create_backup(BackupType.FULL)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(backup.archive_path, "r") as zin, zipfile.ZipFile(tampered, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("blocks/"):
                data = b'{"corrupted": true}'
            zout.writestr(item, data)

    with zipfile.ZipFile(tampered, "r") as zf:
        metadata = json.loads(zf.read("metadata.json"))
        valid = stack.backup_service._verify_checksum(zf, metadata)
        assert valid is False

    stack.close()
    engine.close()
    meta.close()
