"""Tests for HintStore durability."""

import pytest

from node.hint_store import HintStatus, HintStore


@pytest.fixture
def store(tmp_path):
    s = HintStore(tmp_path / "hints.db")
    yield s
    s.close()


def test_create_and_list_pending(store):
    hint = store.create_hint("node2", "b1", 5, {"data": "x", "lsn": 1})
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].hint_id == hint.hint_id


def test_mark_delivered(store):
    hint = store.create_hint("node2", "b1", 5, {"data": "x"})
    store.mark_delivered(hint.hint_id)
    assert len(store.list_pending()) == 0
    updated = store.get_hint(hint.hint_id)
    assert updated.status == HintStatus.DELIVERED
    assert updated.delivered_at is not None


def test_survives_restart(tmp_path):
    db_path = tmp_path / "hints.db"
    store1 = HintStore(db_path)
    hint = store1.create_hint("node2", "b1", 5, {"data": "x"})
    store1.close()

    store2 = HintStore(db_path)
    recovered = store2.get_hint(hint.hint_id)
    assert recovered is not None
    assert recovered.block_id == "b1"
    store2.close()
