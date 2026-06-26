"""Tests for Raft snapshotting."""

import pytest

from metadata.raft.models import CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path, election_min_ms=50, election_max_ms=80)
    yield cluster
    cluster.stop_all()


def test_snapshot_compacts_log(raft_cluster):
    leader = raft_cluster.leader()
    for i in range(12):
        leader.propose(
            CommandType.ADD_ALERT,
            {
                "severity": "INFO",
                "node": "cluster",
                "description": f"alert-{i}",
                "alert_id": f"a-{i}",
            },
        )

    import time
    time.sleep(0.5)
    assert leader.snapshot_index > 0 or len(leader.log) < 12


def test_restore_from_snapshot_on_restart(raft_cluster, tmp_path):
    leader = raft_cluster.leader()
    leader.propose(
        CommandType.REGISTER_NODE,
        {"node_id": "node1", "address": "node1:8001"},
    )
    import time
    time.sleep(0.3)

    node_id = leader.node_id
    raft_cluster.restart_node(node_id)
    restarted = raft_cluster.nodes[node_id]
    time.sleep(0.3)
    assert restarted._state_machine._membership.get_node("node1") is not None
