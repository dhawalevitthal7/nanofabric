"""Data models for snapshots, backups, and restore jobs."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SnapshotStatus(str, Enum):
    CREATING = "CREATING"
    READY = "READY"
    FAILED = "FAILED"
    DELETING = "DELETING"
    RESTORING = "RESTORING"


class SnapshotRecord(BaseModel):
    snapshot_id: str
    timestamp: int
    block_count: int
    metadata_version: int
    status: SnapshotStatus = SnapshotStatus.READY
    size_bytes: int = 0
    placements: Dict[str, List[str]] = Field(default_factory=dict)
    error: Optional[str] = None


class BackupType(str, Enum):
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"


class BackupStatus(str, Enum):
    CREATING = "CREATING"
    READY = "READY"
    FAILED = "FAILED"
    RESTORING = "RESTORING"


class BackupRecord(BaseModel):
    backup_id: str
    backup_type: BackupType
    timestamp: int
    snapshot_ids: List[str] = Field(default_factory=list)
    block_count: int = 0
    size_bytes: int = 0
    status: BackupStatus = BackupStatus.READY
    archive_path: Optional[str] = None
    base_backup_id: Optional[str] = None
    error: Optional[str] = None


class RestoreJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RestoreJob(BaseModel):
    job_id: str
    source_type: str
    source_id: str
    status: RestoreJobStatus = RestoreJobStatus.PENDING
    blocks_restored: int = 0
    placements_restored: int = 0
    created_at: int
    completed_at: Optional[int] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class PolicySchedule(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class SnapshotPolicy(BaseModel):
    policy_id: str
    name: str
    schedule: PolicySchedule
    retention_count: int = Field(default=7, ge=1)
    enabled: bool = True
    last_run_at: Optional[int] = None
    next_run_at: Optional[int] = None
