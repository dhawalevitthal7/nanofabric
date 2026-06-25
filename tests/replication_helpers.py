"""Shared helpers for replication integration tests."""

from typing import Dict, Tuple

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app as create_metadata_app
from node.api_server import create_app as create_node_app
from node.metadata_client import MetadataClient


class RoutingReplicaClient:
    """Replica client that routes HTTP to in-process node TestClients."""

    def __init__(self, node_clients: Dict[str, TestClient]):
        self._node_clients = node_clients

    def replicate_write(self, target_url, target_node, request):
        client = self._node_clients[target_node]
        response = client.post("/replicate", json=request.model_dump())
        if response.status_code == 409:
            from node.replica_client import ReplicaClientError
            raise ReplicaClientError(target_node, response.text, status_code=409)
        if response.status_code >= 400:
            from node.replica_client import ReplicaClientError
            raise ReplicaClientError(
                target_node,
                f"HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        from node.replication_models import ReplicateResponse
        return ReplicateResponse(**response.json())

    def read_block(self, target_url, target_node, block_id):
        client = self._node_clients[target_node]
        response = client.get(f"/read/{block_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            from node.replica_client import ReplicaClientError
            raise ReplicaClientError(
                target_node,
                f"HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        return response.json()

    def replicate_delete(self, target_url, target_node, request):
        client = self._node_clients[target_node]
        response = client.post("/replicate-delete", json=request.model_dump())
        if response.status_code == 409:
            from node.replica_client import ReplicaClientError
            raise ReplicaClientError(target_node, response.text, status_code=409)
        if response.status_code >= 400:
            from node.replica_client import ReplicaClientError
            raise ReplicaClientError(
                target_node,
                f"HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        from node.replication_models import ReplicateResponse
        return ReplicateResponse(**response.json())


class TestMetadataClient(MetadataClient):
    """Metadata client backed by an in-process TestClient."""

    def __init__(self, test_client: TestClient):
        super().__init__(metadata_url="http://test-metadata")
        self._test_client = test_client

    def get_block_locations(self, block_id):
        response = self._test_client.get(f"/blocks/{block_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()["locations"]

    def get_node_addresses(self):
        response = self._test_client.get("/nodes")
        response.raise_for_status()
        nodes = response.json()
        return {node_id: record["address"] for node_id, record in nodes.items()}


class NoPlacementMetadataClient(MetadataClient):
    """Metadata client that reports no placements — for local-only node tests."""

    def get_block_locations(self, block_id):
        return None

    def get_node_addresses(self):
        return {}


class RoutingNodeClient:
    """Node client that routes HTTP to in-process node TestClients."""

    def __init__(self, node_clients: Dict[str, TestClient]):
        self._node_clients = node_clients

    def resolve_url(self, node_id, addresses):
        return f"http://{addresses[node_id]}"

    def list_blocks(self, node_id, addresses):
        client = self._node_clients[node_id]
        response = client.get("/blocks")
        response.raise_for_status()
        return response.json().get("blocks", [])

    def read_block(self, node_id, block_id, addresses):
        client = self._node_clients[node_id]
        response = client.get(f"/read/{block_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            from cluster.node_client import NodeClientError
            raise NodeClientError(node_id, response.text)
        return response.json()

    def get_merkle_root(self, node_id, addresses):
        client = self._node_clients[node_id]
        response = client.get("/merkle")
        response.raise_for_status()
        return response.json()

    def has_block(self, node_id, block_id, addresses):
        record = self.read_block(node_id, block_id, addresses)
        return record is not None and not record.get("deleted", False)

    def replay_hints(self, node_id, addresses):
        client = self._node_clients[node_id]
        response = client.post("/hints/replay")
        response.raise_for_status()
        return response.json().get("delivered", 0)


@pytest.fixture
def repair_cluster(tmp_path):
    """Metadata + 4 nodes wired for Phase 6 repair tests."""
    from metadata import app as metadata_app_module
    from metadata.app import create_app
    from metadata.placement_policy import RoundRobinPlacementPolicy
    from cluster.repair_factory import build_repair_stack
    from cluster.repair_metrics import RepairMetrics

    db_path = tmp_path / "metadata.db"
    app = create_app(db_path=db_path)
    app.state.start_repair_worker = False
    metadata_tc = TestClient(app)
    metadata_tc.__enter__()

    for i in range(1, 5):
        metadata_tc.post(
            "/register",
            json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
        )

    node_clients: Dict[str, TestClient] = {}
    metadata_client = TestMetadataClient(metadata_tc)
    routing_client = RoutingReplicaClient(node_clients)
    routing_node_client = RoutingNodeClient(node_clients)

    for i in range(1, 5):
        node_id = f"node{i}"
        node_app = create_node_app(
            node_id=node_id,
            data_dir=str(tmp_path / node_id),
            metadata_url="http://test-metadata",
            address=f"{node_id}:800{i}",
            metadata_client=metadata_client,
            replica_client=routing_client,
            start_worker=False,
            start_heartbeat=False,
            start_hint_worker=False,
            run_node_recovery=False,
        )
        tc = TestClient(node_app)
        tc.__enter__()
        node_clients[node_id] = tc

    placement = metadata_app_module.get_placement_service()
    registry = metadata_app_module.get_registry()
    policy = RoundRobinPlacementPolicy()
    metadata_app_module._repair_metrics = RepairMetrics()
    metadata_app_module._repair_service = build_repair_stack(
        placement_service=placement,
        membership=registry,
        placement_policy=policy,
        db_path=db_path.parent / "repair.db",
        replica_client=routing_client,
        node_client=routing_node_client,
        metrics=metadata_app_module._repair_metrics,
    )

    yield metadata_tc, node_clients, metadata_client, routing_client, routing_node_client

    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata_tc.__exit__(None, None, None)


@pytest.fixture
def test_cluster(tmp_path) -> Tuple[TestClient, Dict[str, TestClient], TestMetadataClient]:
    """Pytest fixture: metadata + node cluster with replication wired in-process."""
    db_path = tmp_path / "metadata.db"
    metadata_tc = TestClient(create_metadata_app(db_path=db_path))
    metadata_tc.__enter__()

    for i in range(1, 4):
        metadata_tc.post(
            "/register",
            json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
        )

    node_clients: Dict[str, TestClient] = {}
    metadata_client = TestMetadataClient(metadata_tc)
    routing_client = RoutingReplicaClient(node_clients)

    for i in range(1, 4):
        node_id = f"node{i}"
        app = create_node_app(
            node_id=node_id,
            data_dir=str(tmp_path / node_id),
            metadata_url="http://test-metadata",
            address=f"{node_id}:800{i}",
            metadata_client=metadata_client,
            replica_client=routing_client,
            start_worker=False,
            start_heartbeat=False,
            start_hint_worker=False,
        )
        tc = TestClient(app)
        tc.__enter__()
        node_clients[node_id] = tc

    yield metadata_tc, node_clients, metadata_client

    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata_tc.__exit__(None, None, None)
