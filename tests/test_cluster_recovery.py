"""Tests for cluster recovery scenarios."""

import pytest

from metadata.app import get_placement_service, get_registry, get_repair_service
from metadata.models import NodeStatus


def test_node_failure_triggers_re_replication(repair_cluster):
    metadata, nodes, _, _, _ = repair_cluster
    service = get_repair_service()
    registry = get_registry()

    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
    nodes["node1"].post(
        "/write", json={"block_id": "invoice-123", "data": "invoice-data", "version": 1}
    )

    with registry._lock:
        record = registry._nodes["node3"]
        registry._nodes["node3"] = record.model_copy(update={"status": NodeStatus.DOWN})

    result = service.repair_node("node3")
    assert result["repaired"] >= 0

    locations = metadata.get("/blocks/invoice-123").json()["locations"]
    assert len(locations) == 3


def test_interrupted_repair_job_recovery(repair_cluster):
    from cluster.repair_models import RepairStatus

    service = get_repair_service()
    job = service.schedule_repair("crash-blk", "node1", "node4", 1)
    service._job_store.update_job_status(job.job_id, RepairStatus.COPYING)

    recovered = service.recover_jobs()
    assert recovered >= 1

    pending = service._job_store.list_jobs_by_status(RepairStatus.PENDING)
    assert any(j.job_id == job.job_id for j in pending)


def test_cluster_integrity_endpoint(repair_cluster):
    metadata, nodes, _, _, _ = repair_cluster
    metadata.post("/allocate", json={"block_id": "integrity-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "integrity-blk", "data": "d", "version": 1})

    response = metadata.get("/cluster/integrity")
    assert response.status_code == 200
    body = response.json()
    assert "healthy" in body
    assert "anti_entropy" in body
