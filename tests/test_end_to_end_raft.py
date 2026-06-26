"""End-to-end Raft integration tests via HTTP."""

import time

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app
from metadata.raft.config import RaftConfig


@pytest.fixture
def raft_app_client(tmp_path):
    config = RaftConfig(
        enabled=True,
        node_id="metadata1",
        peer_urls={"metadata1": "http://localhost:9001"},
        election_min_ms=100,
        election_max_ms=150,
        advertise_url="http://localhost:9001",
    )
    app = create_app(db_path=tmp_path / "meta.db", raft_config=config)
    app.state.start_repair_worker = False
    with TestClient(app) as client:
        yield client


def test_raft_status_endpoint(raft_app_client):
    resp = raft_app_client.get("/raft/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == "metadata1"
    assert body["role"] in ("FOLLOWER", "CANDIDATE", "LEADER")


def test_raft_leader_endpoint(raft_app_client):
    resp = raft_app_client.get("/raft/leader")
    assert resp.status_code == 200
    assert "term" in resp.json()


def test_raft_metrics_endpoint(raft_app_client):
    resp = raft_app_client.get("/raft/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "raft_current_term" in body
    assert "raft_election_count" in body


def test_single_node_register_with_raft(raft_app_client):
    from metadata.app import get_raft_node

    node = get_raft_node()
    if node and not node.is_leader():
        time.sleep(0.5)

    resp = raft_app_client.post(
        "/register",
        json={"node_id": "node1", "address": "node1:8001"},
    )
    assert resp.status_code in (200, 307)

    if resp.status_code == 200:
        nodes = raft_app_client.get("/nodes").json()
        assert "node1" in nodes


def test_health_includes_raft(raft_app_client):
    resp = raft_app_client.get("/health")
    assert resp.status_code == 200
    assert "raft" in resp.json()
