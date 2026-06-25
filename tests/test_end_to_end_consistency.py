"""End-to-end consistency scenario tests."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app as create_metadata_app
from node.api_server import create_app as create_node_app
from node.replica_client import ReplicaClientError
from node.replication_models import ReplicateResponse
from replication_helpers import RoutingReplicaClient, TestMetadataClient


class SelectiveFailClient:
    """Replica client that can fail specific nodes."""

    def __init__(self, inner, down_nodes=None):
        self._inner = inner
        self._down_nodes = set(down_nodes or [])

    def replicate_write(self, target_url, target_node, request):
        if target_node in self._down_nodes:
            raise ReplicaClientError(target_node, "down")
        return self._inner.replicate_write(target_url, target_node, request)

    def replicate_delete(self, target_url, target_node, request):
        if target_node in self._down_nodes:
            raise ReplicaClientError(target_node, "down")
        return self._inner.replicate_delete(target_url, target_node, request)

    def read_block(self, target_url, target_node, block_id):
        return self._inner.read_block(target_url, target_node, block_id)


@pytest.fixture
def e2e_cluster(tmp_path):
    db_path = tmp_path / "metadata.db"
    metadata_tc = TestClient(create_metadata_app(db_path=db_path))
    metadata_tc.__enter__()

    for i in range(1, 4):
        metadata_tc.post(
            "/register",
            json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
        )

    node_clients = {}
    metadata_client = TestMetadataClient(metadata_tc)
    routing = RoutingReplicaClient(node_clients)

    for i in range(1, 4):
        node_id = f"node{i}"
        app = create_node_app(
            node_id=node_id,
            data_dir=str(tmp_path / node_id),
            metadata_url="http://test-metadata",
            address=f"{node_id}:800{i}",
            metadata_client=metadata_client,
            replica_client=routing,
            start_worker=False,
            start_heartbeat=False,
            start_hint_worker=False,
        )
        tc = TestClient(app)
        tc.__enter__()
        node_clients[node_id] = tc

    metadata_tc.post("/allocate", json={"block_id": "demo-block", "rf": 3})

    yield metadata_tc, node_clients, routing

    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata_tc.__exit__(None, None, None)


def test_scenario1_one_replica_down_write_and_read_succeed(e2e_cluster):
    metadata, nodes, routing = e2e_cluster
    fail_client = SelectiveFailClient(routing, down_nodes={"node3"})

    for node_id in ("node1", "node2", "node3"):
        nodes[node_id].app.state.config["replica_client"] = fail_client
        nodes[node_id].app.state.replication_service._replica_client = fail_client

    resp = nodes["node1"].post(
        "/write", json={"block_id": "demo-block", "data": "hello"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    read_resp = nodes["node1"].post(
        "/read-quorum", json={"block_id": "demo-block"}
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["data"] == "hello"


def test_scenario2_two_replicas_down_write_fails(e2e_cluster):
    metadata, nodes, routing = e2e_cluster
    fail_client = SelectiveFailClient(routing, down_nodes={"node2", "node3"})

    for node_id in ("node1", "node2", "node3"):
        nodes[node_id].app.state.replication_service._replica_client = fail_client

    resp = nodes["node1"].post(
        "/write", json={"block_id": "demo-block", "data": "hello"}
    )
    assert resp.status_code == 503


def test_scenario3_hint_replay_on_recovery(e2e_cluster):
    metadata, nodes, routing = e2e_cluster
    fail_client = SelectiveFailClient(routing, down_nodes={"node3"})

    nodes["node1"].app.state.replication_service._replica_client = fail_client
    nodes["node1"].post("/write", json={"block_id": "demo-block", "data": "hello"})

    pending = nodes["node1"].get("/hints/pending").json()
    assert len(pending) >= 1

    nodes["node1"].app.state.replication_service._replica_client = routing
    replay = nodes["node1"].post("/hints/replay")
    assert replay.status_code == 200
    assert replay.json()["delivered"] >= 1

    read = nodes["node3"].get("/read/demo-block")
    assert read.status_code == 200
    assert read.json()["data"] == "hello"


def test_scenario4_read_repair_restores_stale_replica(e2e_cluster):
    metadata, nodes, routing = e2e_cluster

    nodes["node1"].post("/write", json={"block_id": "demo-block", "data": "v1"})

    fail_client = SelectiveFailClient(routing, down_nodes={"node2"})
    nodes["node1"].app.state.replication_service._replica_client = fail_client
    nodes["node1"].post("/write", json={"block_id": "demo-block", "data": "v2"})

    read_node2 = nodes["node2"].get("/read/demo-block")
    assert read_node2.json()["data"] == "v1"

    nodes["node1"].app.state.replication_service._replica_client = routing
    repair = nodes["node1"].post("/repair", json={"block_id": "demo-block"})
    assert repair.status_code == 200
    assert repair.json()["repaired"] >= 1

    read = nodes["node2"].get("/read/demo-block")
    assert read.json()["data"] == "v2"


def test_merkle_detects_divergence(e2e_cluster):
    _, nodes, _ = e2e_cluster
    nodes["node1"].post("/write", json={"block_id": "demo-block", "data": "a"})
    nodes["node2"].post(
        "/replicate",
        json={
            "block_id": "demo-block",
            "data": "b",
            "version": 2,
            "lsn": 99,
            "origin_node_id": "node1",
        },
    )

    root1 = nodes["node1"].get("/merkle").json()["root_hash"]
    root2 = nodes["node2"].get("/merkle").json()["root_hash"]
    assert root1 != root2
