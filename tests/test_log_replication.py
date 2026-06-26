"""Tests for Raft log replication."""

import time

import pytest

from metadata.raft.models import CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_log_replicates_to_followers(raft_cluster):
    leader = raft_cluster.leader()
    result = leader.propose(
        CommandType.REGISTER_NODE,
        {"node_id": "node1", "address": "node1:8001"},
    )
    assert result.success
    time.sleep(0.2)

    for node_id, node in raft_cluster.nodes.items():
        assert node.commit_index >= 1
        assert raft_cluster.registries[node_id].get_node("node1") is not None


def test_allocate_block_replicates(raft_cluster):
    leader = raft_cluster.leader()
    leader.propose(CommandType.REGISTER_NODE, {"node_id": "node1", "address": "n1:8001"})
    leader.propose(CommandType.REGISTER_NODE, {"node_id": "node2", "address": "n2:8002"})
    leader.propose(CommandType.REGISTER_NODE, {"node_id": "node3", "address": "n3:8003"})

    result = leader.propose(
        CommandType.ALLOCATE_BLOCK,
        {"block_id": "blk-1", "version": 1, "nodes": ["node1", "node2", "node3"]},
    )
    assert result.success
    time.sleep(0.3)

    for node in raft_cluster.nodes.values():
        sm = node._state_machine
        assert sm._placement_registry.block_exists("blk-1")


def test_commit_index_advances_on_majority(raft_cluster):
    leader = raft_cluster.leader()
    before = leader.commit_index
    leader.propose(CommandType.ADD_ALERT, {
        "severity": "INFO",
        "node": "cluster",
        "description": "test alert",
    })
    time.sleep(0.2)
    assert leader.commit_index > before
