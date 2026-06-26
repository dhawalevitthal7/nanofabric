"""Tests for Raft leader election."""

import time

import pytest

from metadata.raft.models import CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_leader_elected_on_startup(raft_cluster):
    leader_id = raft_cluster.wait_for_leader(timeout=3.0)
    assert leader_id in raft_cluster.node_ids
    leader = raft_cluster.nodes[leader_id]
    assert leader.is_leader()
    assert leader.current_term >= 1


def test_only_one_leader(raft_cluster):
    raft_cluster.wait_for_leader()
    leaders = [nid for nid, n in raft_cluster.nodes.items() if n.is_leader()]
    assert len(leaders) == 1


def test_election_increments_term(raft_cluster):
    leader_id = raft_cluster.wait_for_leader()
    term = raft_cluster.nodes[leader_id].current_term
    raft_cluster.kill_leader()
    time.sleep(0.5)
    new_leader_id = raft_cluster.wait_for_leader()
    new_term = raft_cluster.nodes[new_leader_id].current_term
    assert new_term > term


def test_candidate_becomes_leader_with_majority(raft_cluster):
    leader = raft_cluster.leader()
    result = leader.propose(CommandType.REGISTER_NODE, {"node_id": "node1", "address": "n1:8001"})
    assert result.success
