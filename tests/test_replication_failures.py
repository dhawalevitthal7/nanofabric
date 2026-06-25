"""Tests for replication failure handling."""

from unittest.mock import MagicMock

import pytest

from node.metrics import Metrics
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import JobStatus, ReplicationState
from node.replication_service import ReplicationService


@pytest.fixture
def failing_service(tmp_path):
    metadata = MagicMock()
    metadata.get_block_locations.return_value = ["node1", "node2", "node3"]
    metadata.get_node_addresses.return_value = {
        "node1": "node1:8001",
        "node2": "node2:8002",
        "node3": "node3:8003",
    }
    metadata.resolve_node_url.side_effect = lambda node_id, addresses: f"http://{addresses[node_id]}"

    replica_client = MagicMock()
    from node.replica_client import ReplicaClientError
    replica_client.replicate_write.side_effect = ReplicaClientError("node2", "connection refused")

    store = ReplicationJobStore(tmp_path / "replication.db")
    svc = ReplicationService(
        node_id="node1",
        metadata_client=metadata,
        replica_client=replica_client,
        replica_manager=ReplicaManager(),
        job_store=store,
        metrics=Metrics(),
    )
    yield svc, replica_client, store
    store.close()


def test_replica_down_marks_failed_and_creates_jobs(failing_service):
    svc, _, store = failing_service
    result = svc.replicate_write("invoice-1", "hello", 1, 5)
    assert result.state == ReplicationState.FAILED
    assert result.quorum_satisfied is False
    failed_jobs = store.list_jobs_by_status(JobStatus.FAILED)
    assert len(failed_jobs) == 2


def test_retry_failed_replications(failing_service):
    svc, replica_client, store = failing_service
    svc.replicate_write("invoice-1", "hello", 1, 5)

    from node.replication_models import ReplicateResponse
    replica_client.replicate_write.side_effect = None
    replica_client.replicate_write.return_value = ReplicateResponse(
        status="success", node_id="node2", version=1
    )

    retried = svc.retry_failed_replications()
    assert retried == 2
    success_jobs = store.list_jobs_by_status(JobStatus.SUCCESS)
    assert len(success_jobs) == 2
