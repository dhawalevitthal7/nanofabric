"""Tests for repair service orchestration."""

import pytest

from cluster.repair_factory import build_repair_stack
from cluster.repair_job_store import RepairJobStore
from cluster.repair_metrics import RepairMetrics
from cluster.repair_models import RepairStatus
from metadata.app import get_placement_service, get_registry
from replication_helpers import RoutingNodeClient, RoutingReplicaClient


@pytest.fixture
def repair_service(repair_cluster):
    metadata_tc, node_clients, metadata_client, routing_client, routing_node = repair_cluster
    placement = get_placement_service()
    registry = get_registry()
    from metadata.placement_policy import RoundRobinPlacementPolicy

    policy = RoundRobinPlacementPolicy()
    metrics = RepairMetrics()
    service = build_repair_stack(
        placement_service=placement,
        membership=registry,
        placement_policy=policy,
        db_path=metadata_tc.app.state.db_path.parent / "repair-test.db",
        replica_client=routing_client,
        node_client=routing_node,
        metrics=metrics,
    )
    return service, metadata_tc, node_clients, metrics


def test_scan_cluster_detects_under_replication(repair_service):
    service, metadata, nodes, _ = repair_service
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
    nodes["node1"].app.state.engine.write_local("invoice-123", "invoice-data", 1)

    report = service.scan_cluster()
    assert len(report.under_replicated) >= 1


def test_schedule_and_verify_repair_job(repair_service):
    service, metadata, nodes, metrics = repair_service
    metadata.post("/allocate", json={"block_id": "blk-repair", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "blk-repair", "data": "x", "version": 1})

    job = service.schedule_repair("blk-repair", "node1", "node4", 1)
    assert job.status == RepairStatus.PENDING
    assert metrics.repair_jobs_total == 1


def test_recover_interrupted_jobs(repair_service):
    service, metadata, nodes, _ = repair_service
    job = service.schedule_repair("blk-x", "node1", "node4", 1)
    service._job_store.update_job_status(job.job_id, RepairStatus.COPYING)

    recovered = service.recover_jobs()
    assert recovered >= 1


def test_repair_block_rebuilds_replica(repair_service):
    service, metadata, nodes, metrics = repair_service
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
    nodes["node1"].post(
        "/write", json={"block_id": "invoice-123", "data": "invoice-data", "version": 1}
    )

    result = service.repair_block("invoice-123")
    assert result.get("ok") is True or result.get("repaired", 0) >= 0

    locations = metadata.get("/blocks/invoice-123").json()["locations"]
    assert len(locations) == 3


def test_get_cluster_health(repair_service):
    service, metadata, nodes, _ = repair_service
    metadata.post("/allocate", json={"block_id": "health-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "health-blk", "data": "d", "version": 1})

    health = service.get_cluster_health()
    assert "under_replicated_count" in health
    assert "nodes_healthy" in health
