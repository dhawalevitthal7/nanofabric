"""Tests for durable repair job store."""

import pytest

from cluster.repair_job_store import RepairJobStore
from cluster.repair_models import RepairStatus, RepairType


@pytest.fixture
def store(tmp_path):
    s = RepairJobStore(tmp_path / "repair.db")
    yield s
    s.close()


def test_create_and_get_job(store):
    job = store.create_job(
        block_id="blk-1",
        source_node="node1",
        target_node="node4",
        version=1,
        repair_type=RepairType.RE_REPLICATION,
    )
    assert job.status == RepairStatus.PENDING
    assert job.attempt_count == 0

    fetched = store.get_job(job.job_id)
    assert fetched is not None
    assert fetched.block_id == "blk-1"


def test_idempotent_job_creation(store):
    job1 = store.create_job("blk-1", "node1", "node4", 1, RepairType.RE_REPLICATION)
    job2 = store.create_job("blk-1", "node1", "node4", 1, RepairType.RE_REPLICATION)
    assert job1.job_id == job2.job_id


def test_update_status_and_completed_at(store):
    job = store.create_job("blk-1", "node1", "node4", 1, RepairType.RE_REPLICATION)
    store.update_job_status(job.job_id, RepairStatus.COPYING, increment_attempt=True)
    store.update_job_status(job.job_id, RepairStatus.COMPLETED)

    updated = store.get_job(job.job_id)
    assert updated.status == RepairStatus.COMPLETED
    assert updated.completed_at is not None
    assert updated.attempt_count == 1


def test_list_pending_and_failed(store):
    store.create_job("blk-1", "node1", "node4", 1, RepairType.RE_REPLICATION)
    job2 = store.create_job("blk-2", "node1", "node4", 1, RepairType.RE_REPLICATION)
    store.update_job_status(job2.job_id, RepairStatus.FAILED, last_error="timeout")

    pending_failed = store.list_pending_and_failed()
    assert len(pending_failed) == 2


def test_recover_interrupted_jobs(store):
    job = store.create_job("blk-1", "node1", "node4", 1, RepairType.RE_REPLICATION)
    store.update_job_status(job.job_id, RepairStatus.COPYING)

    interrupted = store.list_interrupted_jobs()
    assert len(interrupted) == 1
    assert interrupted[0].job_id == job.job_id
