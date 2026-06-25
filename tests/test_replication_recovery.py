"""Tests for replication recovery after primary restart."""

from unittest.mock import MagicMock

from node.metrics import Metrics
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import JobStatus
from node.replication_service import ReplicationService


def test_pending_jobs_recovered_on_restart(tmp_path):
    db_path = tmp_path / "replication.db"
    store = ReplicationJobStore(db_path)
    store.create_job("invoice-1", 1, "node1", "node2", lsn=5, data="hello")
    store.create_job("invoice-1", 1, "node1", "node3", lsn=5, data="hello")
    store.close()

    metadata = MagicMock()
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

    store2 = ReplicationJobStore(db_path)
    svc = ReplicationService(
        node_id="node1",
        metadata_client=metadata,
        replica_client=replica_client,
        replica_manager=ReplicaManager(),
        job_store=store2,
        metrics=Metrics(),
    )

    recovered = svc.recover_pending_jobs()
    assert recovered == 2
    assert len(store2.list_jobs_by_status(JobStatus.SUCCESS)) == 2
    store2.close()
