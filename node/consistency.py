"""Consistency level definitions for quorum reads and writes."""

from enum import Enum


class ConsistencyLevel(str, Enum):
    ONE = "ONE"
    QUORUM = "QUORUM"
    ALL = "ALL"
