"""Tests for the membership registry."""

from metadata.membership import MembershipRegistry
from metadata.models import NodeStatus


def test_register_node():
    registry = MembershipRegistry(failure_timeout_sec=3)
    record = registry.register("node1", "node1:8001")

    assert record.node_id == "node1"
    assert record.address == "node1:8001"
    assert record.status == NodeStatus.UP
    assert record.last_seen > 0
    assert record.registered_at > 0


def test_heartbeat_updates_last_seen():
    registry = MembershipRegistry(failure_timeout_sec=3)
    registry.register("node1", "node1:8001")

    ts = 1_712_345_678_900
    record = registry.heartbeat("node1", timestamp=ts)
    assert record.last_seen == ts
    assert record.status == NodeStatus.UP


def test_failure_detection():
    registry = MembershipRegistry(failure_timeout_sec=3)
    registry.register("node1", "node1:8001")
    registry.heartbeat("node1", timestamp=1000)

    transitions = registry.check_failures(now_ms=5000)
    assert transitions == [("node1", "DOWN")]

    summary = registry.get_cluster_summary()
    assert summary == {"node1": "DOWN"}


def test_recovery_detection():
    registry = MembershipRegistry(failure_timeout_sec=3)
    registry.register("node2", "node2:8002")
    registry.heartbeat("node2", timestamp=1000)
    registry.check_failures(now_ms=5000)

    record = registry.heartbeat("node2", timestamp=6000)
    assert record.status == NodeStatus.UP
    assert record.recovered_at == 6000
    assert record.failed_at is None


def test_cluster_summary():
    registry = MembershipRegistry(failure_timeout_sec=3)
    registry.register("node1", "node1:8001")
    registry.register("node2", "node2:8002")
    registry.heartbeat("node1", timestamp=1000)
    registry.heartbeat("node2", timestamp=1000)

    registry.check_failures(now_ms=5000)

    summary = registry.get_cluster_summary()
    assert summary == {"node1": "DOWN", "node2": "DOWN"}


def test_remove_node():
    registry = MembershipRegistry()
    registry.register("node1", "node1:8001")
    assert registry.remove("node1") is True
    assert registry.remove("node1") is False
    assert registry.get_cluster_summary() == {}
