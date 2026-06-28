"""Tests for BackupService."""

import json
import zipfile

from storage.models import BackupStatus, BackupType


def test_full_backup_creates_zip(protection_stack, engine, metadata_store):
    engine.write("bk1", "backup-data", version=1)
    metadata_store.save_placement("bk1", 1, ["node1"])

    backup = protection_stack.backup_service.create_backup(BackupType.FULL)
    assert backup.status == BackupStatus.READY
    assert backup.block_count >= 1
    assert backup.archive_path is not None

    with zipfile.ZipFile(backup.archive_path, "r") as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        assert any(n.startswith("blocks/") for n in names)


def test_incremental_backup(protection_stack, engine, metadata_store):
    engine.write("inc1", "v1", version=1)
    metadata_store.save_placement("inc1", 1, ["node1"])

    full = protection_stack.backup_service.create_backup(BackupType.FULL)
    engine.write("inc2", "v2", version=1)
    metadata_store.save_placement("inc2", 1, ["node1"])

    inc = protection_stack.backup_service.create_backup(
        BackupType.INCREMENTAL, base_backup_id=full.backup_id
    )
    assert inc.backup_type == BackupType.INCREMENTAL
    assert inc.base_backup_id == full.backup_id


def test_list_backups(protection_stack, engine):
    engine.write("x", "y", version=1)
    protection_stack.backup_service.create_backup()
    backups = protection_stack.backup_service.list_backups()
    assert len(backups) >= 1
