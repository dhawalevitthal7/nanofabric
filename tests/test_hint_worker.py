"""Tests for HintWorker background delivery."""

from unittest.mock import MagicMock

import pytest

from node.hint_store import HintStore
from node.hint_worker import HintWorker
from node.hinted_handoff import HintedHandoff
from node.metrics import Metrics


@pytest.fixture
def worker_setup(tmp_path):
    store = HintStore(tmp_path / "hints.db")
    replica_client = MagicMock()
    metrics = Metrics()
    resolve = lambda nid, addr: f"http://{addr[nid]}"
    hh = HintedHandoff("node1", store, replica_client, metrics, resolve)
    addresses = {"node2": "node2:8002"}
    worker = HintWorker(hh, lambda: addresses, interval_sec=0.1)
    yield worker, hh, store, replica_client
    worker.stop()
    store.close()


def test_run_once_delivers_pending(worker_setup):
    worker, hh, store, replica_client = worker_setup
    hh.store_hint("node2", "b1", 1, "data", 10)
    delivered = worker.run_once()
    assert delivered == 1
    replica_client.replicate_write.assert_called_once()
