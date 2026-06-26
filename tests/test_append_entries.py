"""Tests for Raft AppendEntries RPC."""

import pytest

from metadata.raft.models import AppendEntriesRequest, LogEntry, CommandType
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_heartbeat_resets_election(raft_cluster):
    follower = raft_cluster.nodes["metadata2"]
    follower.role = follower.role  # ensure started
    req = AppendEntriesRequest(
        term=10,
        leader_id="metadata1",
        prev_log_index=0,
        prev_log_term=0,
        entries=[],
        leader_commit=0,
    )
    resp = follower.handle_append_entries(req)
    assert resp.success is True
    assert follower.role.value == "FOLLOWER"
    assert follower.leader_id == "metadata1"


def test_append_entries_replicates_log(raft_cluster):
    leader_id = raft_cluster.wait_for_leader()
    leader = raft_cluster.nodes[leader_id]
    follower_id = [n for n in raft_cluster.node_ids if n != leader_id][0]
    follower = raft_cluster.nodes[follower_id]

    entry = LogEntry(
        index=1,
        term=leader.current_term,
        command=CommandType.REGISTER_NODE,
        payload={"node_id": "node1", "address": "n1:8001"},
    )
    req = AppendEntriesRequest(
        term=leader.current_term,
        leader_id=leader_id,
        prev_log_index=0,
        prev_log_term=0,
        entries=[entry],
        leader_commit=1,
    )
    resp = follower.handle_append_entries(req)
    assert resp.success is True
    assert len(follower.log) == 1
    assert follower.commit_index == 1


def test_reject_inconsistent_log(raft_cluster):
    follower = raft_cluster.nodes["metadata3"]
    req = AppendEntriesRequest(
        term=5,
        leader_id="metadata1",
        prev_log_index=5,
        prev_log_term=3,
        entries=[],
        leader_commit=0,
    )
    resp = follower.handle_append_entries(req)
    assert resp.success is False


def test_append_entries_http_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from metadata.app import create_app
    from metadata.raft.config import RaftConfig

    config = RaftConfig(
        enabled=True,
        node_id="metadata1",
        peer_urls={"metadata1": "http://localhost:9001"},
    )
    app = create_app(db_path=tmp_path / "meta.db", raft_config=config)
    app.state.start_repair_worker = False
    with TestClient(app) as client:
        resp = client.post(
            "/raft/append-entries",
            json={
                "term": 3,
                "leader_id": "metadata2",
                "prev_log_index": 0,
                "prev_log_term": 0,
                "entries": [],
                "leader_commit": 0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
