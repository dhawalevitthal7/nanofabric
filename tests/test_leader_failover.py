"""Tests for Raft leader failover."""

import time

import pytest

from metadata.raft.models import CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_new_leader_after_crash(raft_cluster):
    old_leader = raft_cluster.wait_for_leader()
    old_term = raft_cluster.nodes[old_leader].current_term
    raft_cluster.kill_leader()
    time.sleep(0.6)
    new_leader = raft_cluster.wait_for_leader()
    assert new_leader != old_leader or raft_cluster.nodes[new_leader].current_term > old_term


def test_old_leader_becomes_follower_on_return(raft_cluster):
    old_leader_id = raft_cluster.wait_for_leader()
    raft_cluster.kill_leader()
    time.sleep(0.6)
    new_leader_id = raft_cluster.wait_for_leader()
    assert new_leader_id != old_leader_id

    raft_cluster.restart_node(old_leader_id)
    time.sleep(0.5)
    restarted = raft_cluster.nodes[old_leader_id]
    assert restarted.is_leader() is False or restarted.current_term >= raft_cluster.nodes[new_leader_id].current_term


def test_cluster_continues_after_failover(raft_cluster):
    leader = raft_cluster.leader()
    leader.propose(CommandType.REGISTER_NODE, {"node_id": "node1", "address": "n1:8001"})
    raft_cluster.kill_leader()
    time.sleep(0.6)
    new_leader = raft_cluster.leader()
    result = new_leader.propose(
        CommandType.REGISTER_NODE,
        {"node_id": "node2", "address": "n2:8002"},
    )
    assert result.success
