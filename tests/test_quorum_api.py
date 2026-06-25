"""API tests for quorum and consistency endpoints."""

from replication_helpers import test_cluster  # noqa: F401


def test_quorum_status_endpoint(test_cluster):
    _, nodes, _ = test_cluster
    metadata, *_ = test_cluster
    metadata.post("/allocate", json={"block_id": "b1", "rf": 3})

    nodes["node1"].post("/write", json={"block_id": "b1", "data": "hello"})
    resp = nodes["node1"].get("/quorum/status", params={"block_id": "b1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["replication_factor"] == 3
    assert body["write_quorum"] == 2


def test_consistency_get_and_set(test_cluster):
    _, nodes, _ = test_cluster
    resp = nodes["node1"].get("/consistency")
    assert resp.json()["level"] == "QUORUM"

    nodes["node1"].post("/consistency", json={"level": "ONE"})
    assert nodes["node1"].get("/consistency").json()["level"] == "ONE"


def test_read_quorum_endpoint(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "b1", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "b1", "data": "hello"})

    resp = nodes["node1"].post(
        "/read-quorum",
        json={"block_id": "b1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == "hello"
    assert resp.json()["quorum_satisfied"] is True


def test_replication_consistency_endpoint(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "b1", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "b1", "data": "hello"})

    resp = nodes["node1"].get("/replication/consistency", params={"block_id": "b1"})
    assert resp.status_code == 200
    assert resp.json()["write_quorum"] == 2


def test_hints_endpoints(test_cluster):
    metadata, nodes, _ = test_cluster
    metadata.post("/allocate", json={"block_id": "b1", "rf": 3})

    resp = nodes["node1"].post("/write", json={"block_id": "b1", "data": "hello"})
    assert resp.status_code == 200

    hints = nodes["node1"].get("/hints")
    assert hints.status_code == 200

    pending = nodes["node1"].get("/hints/pending")
    assert pending.status_code == 200

    replay = nodes["node1"].post("/hints/replay")
    assert replay.status_code == 200
