"""Tests for hinted handoff."""

from unittest.mock import MagicMock

import pytest

from node.hint_store import HintStore
from node.hinted_handoff import HintedHandoff
from node.metrics import Metrics


@pytest.fixture
def handoff(tmp_path):
    store = HintStore(tmp_path / "hints.db")
    replica_client = MagicMock()
    metrics = Metrics()
    resolve = lambda nid, addr: f"http://{addr[nid]}"
    hh = HintedHandoff("node1", store, replica_client, metrics, resolve)
    yield hh, store, replica_client, metrics
    store.close()


def test_store_hint(handoff):
    hh, store, *_ = handoff
    hint = hh.store_hint("node2", "invoice-123", 10, "payload-data", 42)
    assert hint.target_node == "node2"
    assert hint.block_id == "invoice-123"
    assert len(store.list_pending()) == 1


def test_deliver_hint(handoff):
    hh, store, replica_client, metrics = handoff
    hint = hh.store_hint("node2", "invoice-123", 10, "hello", 42)
    addresses = {"node2": "node2:8002"}
    assert hh.deliver_hint(hint, addresses) is True
    assert metrics.hint_deliveries == 1
    updated = store.get_hint(hint.hint_id)
    assert updated.status.value == "DELIVERED"
