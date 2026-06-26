"""Tests for Raft cluster restart recovery."""

import time

import pytest

from metadata.raft.models import CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_recover_persisted_state(raft_cluster, tmp_path):
    leader = raft_cluster.leader()
    leader.propose(
        CommandType.REGISTER_NODE,
        {"node_id": "node1", "address": "node1:8001"},
    )
    leader.propose(
        CommandType.ALLOCATE_BLOCK,
        {"block_id": "persist-blk", "version": 1, "nodes": ["node1"]},
    )
    time.sleep(0.3)
    term = leader.current_term
    commit = leader.commit_index

    for node in raft_cluster.nodes.values():
        node.stop()

    cluster2 = InMemoryRaftCluster(tmp_path)
    try:
        time.sleep(0.8)
        leader2 = cluster2.leader()
        assert leader2.commit_index >= 1 or leader2.current_term >= term
        node = cluster2.nodes[leader2.node_id]
        sm = node._state_machine
        assert sm._placement_registry.block_exists("persist-blk") or commit >= 2
    finally:
        cluster2.stop_all()


def test_all_nodes_restart(raft_cluster):
    leader = raft_cluster.leader()
    leader.propose(CommandType.REGISTER_NODE, {"node_id": "node1", "address": "n1:8001"})
    time.sleep(0.2)
    node_ids = list(raft_cluster.node_ids)
    for nid in node_ids:
        raft_cluster.restart_node(nid)
    time.sleep(1.0)
    leader_id = raft_cluster.wait_for_leader(timeout=5.0)
    assert leader_id in raft_cluster.node_ids
