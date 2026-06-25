"""Models for durable repair jobs and health scan results."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RepairType(str, Enum):
    RE_REPLICATION = "RE_REPLICATION"
    READ_REPAIR = "READ_REPAIR"
    ANTI_ENTROPY = "ANTI_ENTROPY"
    NODE_RECOVERY = "NODE_RECOVERY"
    ORPHAN_CLEANUP = "ORPHAN_CLEANUP"


class RepairStatus(str, Enum):
    PENDING = "PENDING"
    COPYING = "COPYING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class RepairJob:
    job_id: str
    block_id: str
    source_node: str
    target_node: str
    version: int
    repair_type: RepairType
    status: RepairStatus
    attempt_count: int
    last_error: Optional[str]
    created_at: int
    updated_at: int
    completed_at: Optional[int] = None

    def model_dump(self) -> dict:
        return {
            "job_id": self.job_id,
            "block_id": self.block_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "version": self.version,
            "repair_type": self.repair_type.value,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


@dataclass
class UnderReplicatedBlock:
    block_id: str
    version: int
    desired_nodes: List[str]
    present_nodes: List[str]
    missing_nodes: List[str]

    def model_dump(self) -> dict:
        return {
            "block_id": self.block_id,
            "version": self.version,
            "desired_nodes": self.desired_nodes,
            "present_nodes": self.present_nodes,
            "missing_nodes": self.missing_nodes,
        }


@dataclass
class OverReplicatedBlock:
    block_id: str
    version: int
    desired_nodes: List[str]
    extra_nodes: List[str]

    def model_dump(self) -> dict:
        return {
            "block_id": self.block_id,
            "version": self.version,
            "desired_nodes": self.desired_nodes,
            "extra_nodes": self.extra_nodes,
        }


@dataclass
class DivergedBlock:
    block_id: str
    node_hashes: Dict[str, str]

    def model_dump(self) -> dict:
        return {
            "block_id": self.block_id,
            "node_hashes": self.node_hashes,
        }


@dataclass
class OrphanBlock:
    block_id: str
    orphan_type: str
    node_id: Optional[str] = None

    def model_dump(self) -> dict:
        return {
            "block_id": self.block_id,
            "orphan_type": self.orphan_type,
            "node_id": self.node_id,
        }


@dataclass
class ClusterHealthReport:
    under_replicated: List[UnderReplicatedBlock] = field(default_factory=list)
    over_replicated: List[OverReplicatedBlock] = field(default_factory=list)
    diverged: List[DivergedBlock] = field(default_factory=list)
    orphans: List[OrphanBlock] = field(default_factory=list)

    def model_dump(self) -> dict:
        return {
            "under_replicated": [b.model_dump() for b in self.under_replicated],
            "over_replicated": [b.model_dump() for b in self.over_replicated],
            "diverged": [b.model_dump() for b in self.diverged],
            "orphans": [b.model_dump() for b in self.orphans],
        }
