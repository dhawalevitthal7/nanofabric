"""Tests for the node FastAPI service."""

import pytest
from fastapi.testclient import TestClient

from node.api_server import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(
        node_id="node1",
        data_dir=str(tmp_path / "node1"),
        metadata_url="http://localhost:9999",
        address="node1:8001",
    )
    with TestClient(app) as test_client:
        yield test_client


def test_write_and_read(client):
    write_resp = client.post(
        "/write",
        json={"block_id": "invoice-1", "data": "jay data"},
    )
    assert write_resp.status_code == 200

    read_resp = client.get("/read/invoice-1")
    assert read_resp.status_code == 200
    assert read_resp.json()["data"] == "jay data"


def test_read_missing_block_returns_404(client):
    response = client.get("/read/missing")
    assert response.status_code == 404


def test_stats(client):
    client.post("/write", json={"block_id": "s1", "data": "data"})
    stats = client.get("/stats").json()
    assert stats["node_id"] == "node1"
    assert stats["block_count"] == 1


def test_health(client):
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["node_id"] == "node1"
