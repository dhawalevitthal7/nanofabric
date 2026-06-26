"""Raft consensus for highly available metadata cluster."""

from metadata.raft.models import RaftRole
from metadata.raft.node import RaftNode

__all__ = ["RaftNode", "RaftRole"]
