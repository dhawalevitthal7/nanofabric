"""End-to-end replication API tests."""

from replication_helpers import test_cluster  # noqa: F401 — pytest fixture


def test_rf2_single_write_replicates_to_replica(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    response = nodes["node1"].post(
        "/write",
        json={"block_id": "invoice-123", "data": "hello"},
    )
    assert response.status_code == 200

    read_primary = nodes["node1"].get("/read/invoice-123")
    assert read_primary.json()["data"] == "hello"

    read_replica = nodes["node2"].get("/read/invoice-123")
    assert read_replica.status_code == 200
    assert read_replica.json()["data"] == "hello"


def test_rf3_all_replicas_receive_block(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})

    nodes["node1"].post(
        "/write",
        json={"block_id": "invoice-123", "data": "hello"},
    )

    for node_id in ("node1", "node2", "node3"):
        resp = nodes[node_id].get("/read/invoice-123")
        assert resp.status_code == 200
        assert resp.json()["data"] == "hello"


def test_duplicate_replicate_is_idempotent(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    payload = {
        "block_id": "invoice-123",
        "data": "hello",
        "version": 1,
        "lsn": 10,
        "origin_node_id": "node1",
    }
    r1 = nodes["node2"].post("/replicate", json=payload)
    r2 = nodes["node2"].post("/replicate", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

    read_resp = nodes["node2"].get("/read/invoice-123")
    assert read_resp.json()["data"] == "hello"


def test_stale_replicate_rejected(test_cluster):
    _, nodes, _ = test_cluster

    nodes["node2"].post(
        "/replicate",
        json={
            "block_id": "invoice-123",
            "data": "v2",
            "version": 2,
            "lsn": 20,
            "origin_node_id": "node1",
        },
    )

    response = nodes["node2"].post(
        "/replicate",
        json={
            "block_id": "invoice-123",
            "data": "stale",
            "version": 1,
            "lsn": 10,
            "origin_node_id": "node1",
        },
    )
    assert response.status_code == 409


def test_delete_replication(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 2})

    nodes["node1"].post(
        "/write",
        json={"block_id": "invoice-123", "data": "hello"},
    )
    nodes["node1"].delete("/delete/invoice-123")

    assert nodes["node1"].get("/read/invoice-123").status_code == 404
    assert nodes["node2"].get("/read/invoice-123").status_code == 404


def _primary_for_block(metadata, block_id):
    locations = metadata.get(f"/blocks/{block_id}").json()["locations"]
    return locations[0]


def test_replication_state_endpoint(test_cluster):
    metadata, nodes, _ = test_cluster
    block_id = "state-block"
    metadata.post("/allocate", json={"block_id": block_id, "rf": 2})
    primary = _primary_for_block(metadata, block_id)

    nodes[primary].post(
        "/write",
        json={"block_id": block_id, "data": "hello"},
    )

    state = nodes[primary].get(f"/replication/state/{block_id}")
    assert state.status_code == 200
    assert state.json()["state"] == "REPLICATED"


def test_replication_stats_endpoint(test_cluster):
    metadata, nodes, _ = test_cluster
    block_id = "stats-block"
    metadata.post("/allocate", json={"block_id": block_id, "rf": 2})
    primary = _primary_for_block(metadata, block_id)

    nodes[primary].post(
        "/write",
        json={"block_id": block_id, "data": "hello"},
    )

    stats = nodes[primary].get("/replication/stats").json()
    assert stats["successful_replications"] >= 1
