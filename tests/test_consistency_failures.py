"""Write quorum failure scenario tests."""

from unittest.mock import MagicMock

import pytest

from node.errors import QuorumNotSatisfiedError
from node.hint_store import HintStore
from node.hinted_handoff import HintedHandoff
from node.metrics import Metrics
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import ReplicationState
from node.replication_service import ReplicationService
from node.storage_engine import StorageEngine


@pytest.fixture
def quorum_cluster(tmp_path):
    metadata = MagicMock()
    metadata.get_block_locations.return_value = ["node1", "node2", "node3"]
    metadata.get_node_addresses.return_value = {
        "node1": "node1:8001",
        "node2": "node2:8002",
        "node3": "node3:8003",
    }
    metadata.resolve_node_url.side_effect = lambda nid, addr: f"http://{addr[nid]}"

    replica_client = MagicMock()
    hint_store = HintStore(tmp_path / "hints.db")
    metrics = Metrics()
    hh = HintedHandoff(
        "node1", hint_store, replica_client, metrics, metadata.resolve_node_url
    )

    svc = ReplicationService(
        node_id="node1",
        metadata_client=metadata,
        replica_client=replica_client,
        replica_manager=ReplicaManager(),
        job_store=ReplicationJobStore(tmp_path / "jobs.db"),
        metrics=metrics,
        hinted_handoff=hh,
    )

    engine = StorageEngine(tmp_path / "node1", node_id="node1")
    engine.set_replication_service(svc)

    yield engine, svc, replica_client, hint_store, metrics
    engine.close()
    hint_store.close()
    svc._job_store.close()


def test_scenario1_one_replica_down_succeeds(quorum_cluster):
    """RF=3 W=2: node1+node2 ACK, node3 failed -> SUCCESS."""
    engine, svc, replica_client, hint_store, _ = quorum_cluster
    from node.replica_client import ReplicaClientError
    from node.replication_models import ReplicateResponse

    def side_effect(url, target, request):
        if target == "node2":
            return ReplicateResponse(status="success", node_id="node2", version=1)
        raise ReplicaClientError("node3", "down")

    replica_client.replicate_write.side_effect = side_effect
    engine.write("invoice-123", "hello")
    result = svc.get_last_quorum_snapshot()
    assert result["quorum_satisfied"] is True
    assert result["ack_count"] == 2
    assert len(hint_store.list_pending()) == 1


def test_scenario2_two_replicas_down_fails(quorum_cluster):
    """RF=3 W=2: only node1 ACK -> FAILURE."""
    engine, svc, replica_client, *_ = quorum_cluster
    from node.replica_client import ReplicaClientError

    replica_client.replicate_write.side_effect = ReplicaClientError("node2", "down")
    with pytest.raises(QuorumNotSatisfiedError) as exc:
        engine.write("invoice-123", "hello")
    assert exc.value.acks == 1
    assert exc.value.required == 2
    result = svc.get_last_quorum_snapshot()
    assert result["quorum_satisfied"] is False


def test_partial_success_marks_degraded_not_failed(quorum_cluster):
    engine, svc, replica_client, *_ = quorum_cluster
    from node.replica_client import ReplicaClientError
    from node.replication_models import ReplicateResponse

    def side_effect(url, target, request):
        if target == "node2":
            return ReplicateResponse(status="success", node_id="node2", version=1)
        raise ReplicaClientError("node3", "down")

    replica_client.replicate_write.side_effect = side_effect
    engine.write("b1", "data")
    state = svc._replica_manager.get_replica_state("b1")
    assert state.state == ReplicationState.DEGRADED
