"""Tests for quorum calculation."""

import pytest

from node.consistency import ConsistencyLevel
from node.quorum import (
    calculate_read_quorum,
    calculate_write_quorum,
    is_quorum_satisfied,
    required_acks,
    required_reads,
)


@pytest.mark.parametrize(
    "rf,expected",
    [(1, 1), (2, 2), (3, 2), (5, 3)],
)
def test_write_quorum(rf, expected):
    assert calculate_write_quorum(rf) == expected


@pytest.mark.parametrize(
    "rf,expected",
    [(1, 1), (2, 2), (3, 2), (5, 3)],
)
def test_read_quorum(rf, expected):
    assert calculate_read_quorum(rf) == expected


def test_r_plus_w_greater_than_rf():
    for rf in range(1, 6):
        w = calculate_write_quorum(rf)
        r = calculate_read_quorum(rf)
        assert r + w > rf


def test_required_acks_consistency_levels():
    assert required_acks(3, ConsistencyLevel.ONE) == 1
    assert required_acks(3, ConsistencyLevel.QUORUM) == 2
    assert required_acks(3, ConsistencyLevel.ALL) == 3


def test_required_reads_consistency_levels():
    assert required_reads(3, ConsistencyLevel.ONE) == 1
    assert required_reads(3, ConsistencyLevel.QUORUM) == 2
    assert required_reads(3, ConsistencyLevel.ALL) == 3


def test_is_quorum_satisfied():
    assert is_quorum_satisfied(2, 2) is True
    assert is_quorum_satisfied(1, 2) is False
