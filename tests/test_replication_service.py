"""Tests for ReplicationService orchestration."""

from unittest.mock import MagicMock

import pytest

from node.hint_store import HintStore
from node.hinted_handoff import HintedHandoff
from node.metrics import Metrics
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import ReplicationState
from node.replication_service import ReplicationService


@pytest.fixture
def service(tmp_path):
    metadata = MagicMock()
    metadata.get_block_locations.return_value = ["node1", "node2", "node3"]
    metadata.get_node_addresses.return_value = {
        "node1": "node1:8001",
        "node2": "node2:8002",
        "node3": "node3:8003",
    }
    metadata.resolve_node_url.side_effect = lambda node_id, addresses: f"http://{addresses[node_id]}"

    replica_client = MagicMock()
    from node.replication_models import ReplicateResponse
    replica_client.replicate_write.return_value = ReplicateResponse(
        status="success", node_id="node2", version=1
    )

    mgr = ReplicaManager()
    store = ReplicationJobStore(tmp_path / "replication.db")
    metrics = Metrics()
    hint_store = HintStore(tmp_path / "hints.db")
    hh = HintedHandoff("node1", hint_store, replica_client, metrics, metadata.resolve_node_url)

    svc = ReplicationService(
        node_id="node1",
        metadata_client=metadata,
        replica_client=replica_client,
        replica_manager=mgr,
        job_store=store,
        metrics=metrics,
        hinted_handoff=hh,
    )
    yield svc, replica_client, metadata, store, mgr, metrics, hint_store
    store.close()
    hint_store.close()


def test_replicate_write_rf3(service):
    svc, replica_client, *_ = service
    result = svc.replicate_write("invoice-123", "hello", 1, 10)
    assert result.quorum_satisfied is True
    assert result.state == ReplicationState.REPLICATED
    assert replica_client.replicate_write.call_count == 2


def test_replicate_write_rf2(service):
    svc, replica_client, metadata, *_ = service
    metadata.get_block_locations.return_value = ["node1", "node2"]
    result = svc.replicate_write("invoice-123", "hello", 1, 10)
    assert result.quorum_satisfied is True
    assert replica_client.replicate_write.call_count == 1


def test_replicate_write_no_placement(service):
    svc, replica_client, metadata, *_ = service
    metadata.get_block_locations.return_value = None
    result = svc.replicate_write("invoice-123", "hello", 1, 10)
    assert result.quorum_satisfied is True
    replica_client.replicate_write.assert_not_called()


def test_partial_failure_quorum_satisfied(service):
    svc, replica_client, metadata, _, mgr, metrics, hint_store = service
    from node.replica_client import ReplicaClientError

    def side_effect(url, target, request):
        if target == "node2":
            from node.replication_models import ReplicateResponse
            return ReplicateResponse(status="success", node_id="node2", version=1)
        raise ReplicaClientError("node3", "down")

    replica_client.replicate_write.side_effect = side_effect
    result = svc.replicate_write("invoice-123", "hello", 1, 10)
    assert result.quorum_satisfied is True
    assert result.ack_count == 2
    assert mgr.get_replica_state("invoice-123").state == ReplicationState.DEGRADED
    assert metrics.degraded_replications == 1
    assert len(hint_store.list_pending()) == 1


def test_all_failures_quorum_not_satisfied(service):
    svc, replica_client, *_ = service
    from node.replica_client import ReplicaClientError

    replica_client.replicate_write.side_effect = ReplicaClientError("node2", "down")
    result = svc.replicate_write("invoice-123", "hello", 1, 10)
    assert result.quorum_satisfied is False
    assert result.state == ReplicationState.FAILED
