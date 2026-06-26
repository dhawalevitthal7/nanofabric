"""Tests for Raft network partition behavior."""

import time

import pytest

from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_majority_partition_elects_leader(raft_cluster):
    raft_cluster.wait_for_leader()
    raft_cluster.partition(["metadata3"])
    time.sleep(0.8)
    leaders = [n for n in raft_cluster.nodes.values() if n.is_leader() and n.node_id != "metadata3"]
    assert len(leaders) >= 1


def test_minority_partition_no_leader(raft_cluster):
    raft_cluster.wait_for_leader()
    raft_cluster.partition(["metadata1", "metadata2"])
    time.sleep(0.8)
    isolated_leader = raft_cluster.nodes["metadata3"].is_leader()
    assert isolated_leader is False or raft_cluster.nodes["metadata3"].leader_id is None


def test_heal_partition_restores_consensus(raft_cluster):
    raft_cluster.wait_for_leader()
    raft_cluster.partition(["metadata3"])
    time.sleep(0.5)
    raft_cluster.heal()
    time.sleep(0.8)
    leader_id = raft_cluster.wait_for_leader()
    assert leader_id in raft_cluster.node_ids
