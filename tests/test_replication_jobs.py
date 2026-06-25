"""Tests for ReplicationJobStore persistence."""

from node.replication_job_store import ReplicationJobStore
from node.replication_models import JobStatus


def test_create_and_update_job(tmp_path):
    store = ReplicationJobStore(tmp_path / "replication.db")
    job = store.create_job(
        block_id="invoice-1",
        version=1,
        primary_node="node1",
        target_node="node2",
        lsn=10,
        data="hello",
    )
    assert job.status == JobStatus.PENDING
    assert job.attempt_count == 0

    store.update_job_status(job.job_id, JobStatus.SUCCESS)
    updated = store.get_job(job.job_id)
    assert updated.status == JobStatus.SUCCESS

    store.close()


def test_list_pending_and_failed(tmp_path):
    store = ReplicationJobStore(tmp_path / "replication.db")
    j1 = store.create_job("b1", 1, "node1", "node2", lsn=1, data="a")
    store.create_job("b2", 1, "node1", "node3", lsn=1, data="b")
    store.update_job_status(j1.job_id, JobStatus.FAILED, last_error="timeout")

    pending_failed = store.list_pending_and_failed()
    assert len(pending_failed) == 2
    store.close()


def test_delete_job_persists_across_restart(tmp_path):
    db_path = tmp_path / "replication.db"
    store = ReplicationJobStore(db_path)
    job = store.create_job("invoice-1", 1, "node1", "node2", lsn=5, data="hello")
    store.close()

    store2 = ReplicationJobStore(db_path)
    loaded = store2.get_job(job.job_id)
    assert loaded.block_id == "invoice-1"
    assert loaded.data == "hello"
    store2.close()
