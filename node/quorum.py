"""Quorum calculation utilities."""

import math

from node.consistency import ConsistencyLevel


def calculate_write_quorum(replication_factor: int) -> int:
    """W = floor(RF / 2) + 1"""
    if replication_factor < 1:
        raise ValueError("replication_factor must be >= 1")
    return math.floor(replication_factor / 2) + 1


def calculate_read_quorum(replication_factor: int) -> int:
    """R = floor(RF / 2) + 1"""
    if replication_factor < 1:
        raise ValueError("replication_factor must be >= 1")
    return math.floor(replication_factor / 2) + 1


def required_acks(
    replication_factor: int,
    consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
) -> int:
    if consistency == ConsistencyLevel.ONE:
        return 1
    if consistency == ConsistencyLevel.ALL:
        return replication_factor
    return calculate_write_quorum(replication_factor)


def required_reads(
    replication_factor: int,
    consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
) -> int:
    if consistency == ConsistencyLevel.ONE:
        return 1
    if consistency == ConsistencyLevel.ALL:
        return replication_factor
    return calculate_read_quorum(replication_factor)


def is_quorum_satisfied(acks: int, required: int) -> bool:
    return acks >= required
