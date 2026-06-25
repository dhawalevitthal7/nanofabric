"""Tests for background repair worker."""

import pytest

from cluster.repair_worker import RepairWorker
from metadata.app import get_repair_service


def test_worker_run_once(repair_cluster):
    metadata, nodes, _, _, _ = repair_cluster
    service = get_repair_service()

    metadata.post("/allocate", json={"block_id": "worker-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "worker-blk", "data": "d", "version": 1})

    worker = RepairWorker(service, interval_sec=0.01)
    result = worker.run_once()
    assert "scheduled" in result
    assert "executed" in result


def test_worker_recovers_on_start(repair_cluster):
    from cluster.repair_models import RepairStatus

    service = get_repair_service()
    job = service.schedule_repair("blk-recover", "node1", "node4", 1)
    service._job_store.update_job_status(job.job_id, RepairStatus.COPYING)

    worker = RepairWorker(service, interval_sec=0.01)
    worker.start()
    worker.stop()
