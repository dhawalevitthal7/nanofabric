"""Pydantic models for replication requests, responses, and job state."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ReplicationState(str, Enum):
    PENDING = "PENDING"
    WRITING = "WRITING"
    REPLICATING = "REPLICATING"
    REPLICATED = "REPLICATED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"


class ReplicaStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ReplicateRequest(BaseModel):
    block_id: str = Field(..., min_length=1)
    data: str
    version: int = Field(..., ge=1)
    lsn: int = Field(..., ge=1)
    origin_node_id: str = Field(..., min_length=1)


class ReplicateDeleteRequest(BaseModel):
    block_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    lsn: int = Field(..., ge=1)
    origin_node_id: str = Field(..., min_length=1)


class ReplicateResponse(BaseModel):
    status: str
    node_id: str
    version: int


class ReplicationJob(BaseModel):
    job_id: str
    block_id: str
    version: int
    primary_node: str
    target_node: str
    status: JobStatus
    attempt_count: int = 0
    last_error: Optional[str] = None
    is_delete: bool = False
    data: Optional[str] = None
    lsn: int = 0
    created_at: int = 0
    updated_at: int = 0


class BlockReplicationState(BaseModel):
    block_id: str
    version: int
    replicas: List[str]
    state: ReplicationState


class WriteQuorumResult(BaseModel):
    state: ReplicationState
    quorum_satisfied: bool
    ack_count: int
    required_acks: int
    replication_factor: int
    acked_nodes: List[str] = Field(default_factory=list)
    failed_nodes: List[str] = Field(default_factory=list)
    outcome: str = "SUCCESS"
    latency_ms: float = 0.0
