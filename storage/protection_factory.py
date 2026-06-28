"""Wire data protection components together."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from storage.backup_service import BackupService
from storage.metrics import ProtectionMetrics
from storage.restore_service import RestoreService
from storage.retention_manager import RetentionManager
from storage.snapshot_manager import SnapshotManager
from storage.snapshot_scheduler import SnapshotScheduler
from storage.snapshot_store import SnapshotStore


@dataclass
class ProtectionStack:
    store: SnapshotStore
    snapshot_manager: SnapshotManager
    backup_service: BackupService
    restore_service: RestoreService
    retention_manager: RetentionManager
    scheduler: SnapshotScheduler
    metrics: ProtectionMetrics

    def recover(self) -> None:
        self.store.recover_interrupted_snapshots()
        self.restore_service.recover_interrupted_restores()
        self.backup_service.recover_interrupted_backups()

    def start_scheduler(self) -> None:
        self.scheduler.start()

    def stop_scheduler(self) -> None:
        self.scheduler.stop()

    def close(self) -> None:
        self.stop_scheduler()
        self.store.close()


def build_protection_stack(
    data_dir: str | Path,
    read_blocks,
    write_blocks,
    get_metadata_version: Callable[[], int],
    get_placements: Callable[[], Dict[str, List[str]]],
    restore_placement: Callable[[str, int, List[str]], None],
    clear_blocks: Optional[Callable[[], None]] = None,
    start_scheduler: bool = False,
) -> ProtectionStack:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    metrics = ProtectionMetrics()
    store = SnapshotStore(data_dir / "snapshots.db")
    snapshot_manager = SnapshotManager(
        store=store,
        read_blocks=read_blocks,
        get_metadata_version=get_metadata_version,
        get_placements=get_placements,
        metrics=metrics,
    )
    retention_manager = RetentionManager(store, snapshot_manager, metrics)
    restore_service = RestoreService(
        store=store,
        snapshot_manager=snapshot_manager,
        write_blocks=write_blocks,
        restore_placement=restore_placement,
        clear_blocks=clear_blocks,
        metrics=metrics,
    )
    backup_service = BackupService(
        store=store,
        snapshot_manager=snapshot_manager,
        backup_dir=data_dir / "backups",
        get_placements=get_placements,
        get_metadata_version=get_metadata_version,
        metrics=metrics,
    )
    scheduler = SnapshotScheduler(store, snapshot_manager, retention_manager)

    stack = ProtectionStack(
        store=store,
        snapshot_manager=snapshot_manager,
        backup_service=backup_service,
        restore_service=restore_service,
        retention_manager=retention_manager,
        scheduler=scheduler,
        metrics=metrics,
    )
    stack.recover()

    if start_scheduler:
        stack.start_scheduler()

    return stack
