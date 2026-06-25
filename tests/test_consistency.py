"""Tests for consistency level enum and behaviour."""

from node.consistency import ConsistencyLevel
from node.quorum import required_acks, required_reads


def test_consistency_enum_values():
    assert ConsistencyLevel.ONE.value == "ONE"
    assert ConsistencyLevel.QUORUM.value == "QUORUM"
    assert ConsistencyLevel.ALL.value == "ALL"


def test_one_minimum_acknowledgements():
    assert required_acks(5, ConsistencyLevel.ONE) == 1
    assert required_reads(5, ConsistencyLevel.ONE) == 1


def test_quorum_majority():
    assert required_acks(5, ConsistencyLevel.QUORUM) == 3
    assert required_reads(5, ConsistencyLevel.QUORUM) == 3


def test_all_requires_every_replica():
    assert required_acks(3, ConsistencyLevel.ALL) == 3
    assert required_reads(3, ConsistencyLevel.ALL) == 3
