"""Tests for QuorumManager."""

from node.consistency import ConsistencyLevel
from node.quorum_manager import QuorumManager, QuorumOutcome


def test_quorum_success_rf3_w2():
    mgr = QuorumManager(3, ConsistencyLevel.QUORUM)
    mgr.record_ack("node1")
    mgr.record_ack("node2")
    mgr.record_failure("node3")
    assert mgr.evaluate() == QuorumOutcome.SUCCESS
    assert mgr.ack_count == 2


def test_quorum_failure_rf3_w2():
    mgr = QuorumManager(3, ConsistencyLevel.QUORUM)
    mgr.record_ack("node1")
    mgr.record_failure("node2")
    mgr.record_failure("node3")
    assert mgr.evaluate() == QuorumOutcome.FAILED
    assert mgr.ack_count == 1


def test_snapshot():
    mgr = QuorumManager(3, ConsistencyLevel.QUORUM)
    mgr.record_ack("node1")
    snap = mgr.snapshot()
    assert snap["replication_factor"] == 3
    assert snap["required_acks"] == 2
    assert snap["ack_count"] == 1
