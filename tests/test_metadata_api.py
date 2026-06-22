"""Tests for the metadata FastAPI service."""

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_register_and_list_nodes(client):
    response = client.post(
        "/register",
        json={"node_id": "node1", "address": "node1:8001"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "UP"

    nodes = client.get("/nodes").json()
    assert "node1" in nodes
    assert nodes["node1"]["address"] == "node1:8001"


def test_heartbeat_updates_node(client):
    client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    response = client.post(
        "/heartbeat",
        json={"node_id": "node1", "timestamp": 1_712_345_678_900},
    )
    assert response.status_code == 200
    assert response.json()["last_seen"] == 1_712_345_678_900


def test_heartbeat_unknown_node_returns_404(client):
    response = client.post("/heartbeat", json={"node_id": "missing"})
    assert response.status_code == 404


def test_cluster_summary(client):
    client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    client.post("/register", json={"node_id": "node2", "address": "node2:8002"})

    summary = client.get("/cluster-summary").json()
    assert summary == {"node1": "UP", "node2": "UP"}


def test_health_endpoint(client):
    client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["nodes_total"] == 1
    assert health["nodes_up"] == 1
