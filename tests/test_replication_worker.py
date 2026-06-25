"""Tests for ReplicationWorker background retries."""

from unittest.mock import MagicMock

from node.replication_worker import ReplicationWorker


def test_worker_run_once_delegates_to_service():
    service = MagicMock()
    service.retry_failed_replications.return_value = 3
    worker = ReplicationWorker(service, interval_sec=60)
    assert worker.run_once() == 3
    service.retry_failed_replications.assert_called_once()


def test_worker_start_recovers_pending_jobs():
    service = MagicMock()
    service.node_id = "node1"
    service.recover_pending_jobs.return_value = 2
    service.retry_failed_replications.return_value = 0

    worker = ReplicationWorker(service, interval_sec=60)
    worker.start()
    service.recover_pending_jobs.assert_called_once()
    worker.stop()
