"""Tests for ReplicaManager state transitions."""

from node.replica_manager import ReplicaManager
from node.replication_models import ReplicationState


def test_mark_pending_and_replicated():
    mgr = ReplicaManager()
    state = mgr.mark_pending("invoice-1", 1, ["node1", "node2"])
    assert state.state == ReplicationState.PENDING
    assert state.replicas == ["node1", "node2"]

    mgr.mark_replicating("invoice-1")
    assert mgr.get_replica_state("invoice-1").state == ReplicationState.REPLICATING

    mgr.mark_replicated("invoice-1")
    assert mgr.get_replica_state("invoice-1").state == ReplicationState.REPLICATED


def test_mark_failed_and_degraded():
    mgr = ReplicaManager()
    mgr.mark_pending("invoice-2", 1, ["node1", "node2", "node3"])

    mgr.mark_failed("invoice-2")
    assert mgr.get_replica_state("invoice-2").state == ReplicationState.FAILED
    assert mgr.list_failed_replications()

    mgr.mark_pending("invoice-3", 1, ["node1", "node2"])
    mgr.mark_degraded("invoice-3")
    assert mgr.get_replica_state("invoice-3").state == ReplicationState.DEGRADED
    assert len(mgr.list_failed_replications()) == 2


def test_get_replica_state_missing():
    mgr = ReplicaManager()
    assert mgr.get_replica_state("missing") is None
