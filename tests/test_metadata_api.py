"""Tests for the metadata FastAPI service."""

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "metadata.db"
    with TestClient(create_app(db_path=db_path)) as test_client:
        yield test_client, db_path


def _register_nodes(client, count=3):
    for i in range(1, count + 1):
        client.post(
            "/register",
            json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
        )


def test_register_and_list_nodes(client):
    test_client, _ = client
    response = test_client.post(
        "/register",
        json={"node_id": "node1", "address": "node1:8001"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "UP"

    nodes = test_client.get("/nodes").json()
    assert "node1" in nodes
    assert nodes["node1"]["address"] == "node1:8001"


def test_heartbeat_updates_node(client):
    test_client, _ = client
    test_client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    response = test_client.post(
        "/heartbeat",
        json={"node_id": "node1", "timestamp": 1_712_345_678_900},
    )
    assert response.status_code == 200
    assert response.json()["last_seen"] == 1_712_345_678_900


def test_heartbeat_with_node_stats(client):
    test_client, db_path = client
    test_client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    response = test_client.post(
        "/heartbeat",
        json={
            "node_id": "node1",
            "timestamp": 1000,
            "block_count": 120,
            "used_bytes": 10485760,
            "last_lsn": 4200,
        },
    )
    assert response.status_code == 200

    from metadata.metadata_store import MetadataStore

    store = MetadataStore(db_path)
    row = store._conn.execute(
        "SELECT block_count, used_bytes, last_lsn FROM nodes WHERE node_id = ?",
        ("node1",),
    ).fetchone()
    assert row["block_count"] == 120
    assert row["used_bytes"] == 10485760
    assert row["last_lsn"] == 4200
    store.close()


def test_heartbeat_unknown_node_returns_404(client):
    test_client, _ = client
    response = test_client.post("/heartbeat", json={"node_id": "missing"})
    assert response.status_code == 404


def test_cluster_summary(client):
    test_client, _ = client
    test_client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    test_client.post("/register", json={"node_id": "node2", "address": "node2:8002"})

    summary = test_client.get("/cluster-summary").json()
    assert summary == {"node1": "UP", "node2": "UP"}


def test_health_endpoint(client):
    test_client, _ = client
    test_client.post("/register", json={"node_id": "node1", "address": "node1:8001"})
    health = test_client.get("/health").json()
    assert health["status"] == "ok"
    assert health["nodes_total"] == 1
    assert health["nodes_up"] == 1


def test_allocate_endpoint(client):
    test_client, _ = client
    _register_nodes(test_client)

    response = test_client.post(
        "/allocate",
        json={"block_id": "invoice-123", "rf": 2},
    )
    assert response.status_code == 200
    assert response.json()["nodes"] == ["node1", "node2"]


def test_get_block_locations(client):
    test_client, _ = client
    _register_nodes(test_client)
    test_client.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    response = test_client.get("/blocks/invoice-123")
    assert response.status_code == 200
    assert response.json()["locations"] == ["node1", "node2"]


def test_get_block_locations_not_found(client):
    test_client, _ = client
    response = test_client.get("/blocks/missing")
    assert response.status_code == 404


def test_list_placements(client):
    test_client, _ = client
    _register_nodes(test_client)
    test_client.post("/allocate", json={"block_id": "invoice-1", "rf": 1})
    test_client.post("/allocate", json={"block_id": "invoice-2", "rf": 1})

    placements = test_client.get("/placements").json()
    assert "invoice-1" in placements
    assert "invoice-2" in placements


def test_node_blocks_inventory(client):
    test_client, _ = client
    _register_nodes(test_client)
    test_client.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    response = test_client.get("/nodes/node1/blocks")
    assert response.status_code == 200
    assert response.json()["blocks"] == ["invoice-123"]


def test_metadata_stats(client):
    test_client, _ = client
    _register_nodes(test_client)
    test_client.post("/allocate", json={"block_id": "invoice-1", "rf": 2})
    test_client.post("/allocate", json={"block_id": "invoice-2", "rf": 1})

    stats = test_client.get("/metadata/stats").json()
    assert stats["total_blocks"] == 2
    assert stats["total_placements"] == 3


def test_placement_survives_restart(client):
    test_client, db_path = client
    _register_nodes(test_client)
    test_client.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    with TestClient(create_app(db_path=db_path)) as restarted:
        _register_nodes(restarted)
        response = restarted.get("/blocks/invoice-123")
        assert response.status_code == 200
        assert response.json()["locations"] == ["node1", "node2"]
