"""Raft protocol models, roles, and command types."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RaftRole(str, Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class CommandType(str, Enum):
    REGISTER_NODE = "REGISTER_NODE"
    UPDATE_HEARTBEAT = "UPDATE_HEARTBEAT"
    ALLOCATE_BLOCK = "ALLOCATE_BLOCK"
    UPDATE_PLACEMENT = "UPDATE_PLACEMENT"
    CREATE_REPAIR = "CREATE_REPAIR"
    DELETE_REPAIR = "DELETE_REPAIR"
    ADD_ALERT = "ADD_ALERT"
    ADD_PEER = "ADD_PEER"
    REMOVE_PEER = "REMOVE_PEER"
    RECONFIGURE_CLUSTER = "RECONFIGURE_CLUSTER"


class LogEntry(BaseModel):
    index: int
    term: int
    command: CommandType
    payload: Dict[str, Any] = Field(default_factory=dict)


class RequestVoteRequest(BaseModel):
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


class RequestVoteResponse(BaseModel):
    term: int
    vote_granted: bool


class AppendEntriesRequest(BaseModel):
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: List[LogEntry] = Field(default_factory=list)
    leader_commit: int


class AppendEntriesResponse(BaseModel):
    term: int
    success: bool
    match_index: int = 0


class RaftStatusResponse(BaseModel):
    node_id: str
    leader: Optional[str]
    term: int
    role: RaftRole
    commit_index: int
    last_applied: int
    log_length: int
    peers: List[str]
    replication_lag: int = 0


class RaftLeaderResponse(BaseModel):
    leader: Optional[str]
    term: int
    role: RaftRole
    leader_url: Optional[str] = None


class ElectionEvent(BaseModel):
    term: int
    winner: Optional[str]
    timestamp: int
    reason: str


class ProposeResult(BaseModel):
    success: bool
    index: int = 0
    error: Optional[str] = None
