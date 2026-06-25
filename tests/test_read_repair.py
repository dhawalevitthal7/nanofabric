"""Tests for read repair."""

from unittest.mock import MagicMock

import pytest

from node.metrics import Metrics
from node.read_repair import ReadRepair
from node.version_reconciliation import ReplicaCopy


@pytest.fixture
def repair():
    replica_client = MagicMock()
    metrics = Metrics()
    resolve = lambda nid, addr: f"http://{addr[nid]}"
    rr = ReadRepair("node1", replica_client, metrics, resolve)
    yield rr, replica_client, metrics
    rr.shutdown()


def test_repair_sync(repair):
    rr, replica_client, metrics = repair
    latest = ReplicaCopy("node1", "b1", "data-v2", version=2, lsn=10)
    stale = [ReplicaCopy("node2", "b1", "data-v1", version=1, lsn=5)]
    addresses = {"node2": "node2:8002"}
    count = rr.repair_sync(latest, stale, addresses)
    assert count == 1
    assert metrics.read_repairs == 1
    replica_client.replicate_write.assert_called_once()
