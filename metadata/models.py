"""Pydantic models for metadata service requests and responses."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class RegisterRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    address: str = Field(..., min_length=1)


class HeartbeatRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    timestamp: Optional[int] = None
    block_count: Optional[int] = None
    used_bytes: Optional[int] = None
    last_lsn: Optional[int] = None


class AllocateRequest(BaseModel):
    block_id: str = Field(..., min_length=1)
    rf: int = Field(default=1, ge=1)


class AllocateResponse(BaseModel):
    nodes: list[str]


class BlockLocationsResponse(BaseModel):
    locations: list[str]


class MetadataStatsResponse(BaseModel):
    total_blocks: int
    total_placements: int


class NodeRecord(BaseModel):
    node_id: str
    status: NodeStatus
    address: str
    last_seen: int
    registered_at: int
    failed_at: Optional[int] = None
    recovered_at: Optional[int] = None


class WriteRequest(BaseModel):
    block_id: str = Field(..., min_length=1)
    data: str
    version: Optional[int] = None
