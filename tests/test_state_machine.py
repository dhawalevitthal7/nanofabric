"""Tests for the Raft state machine."""

import pytest

from metadata.membership import MembershipRegistry
from metadata.metadata_store import MetadataStore
from metadata.node_inventory import NodeInventory
from metadata.placement_registry import PlacementRegistry
from metadata.raft.alert_store import AlertStore
from metadata.raft.models import CommandType, LogEntry
from metadata.raft.state_machine import RaftStateMachine


@pytest.fixture
def state_machine(tmp_path):
    store = MetadataStore(tmp_path / "meta.db")
    sm = RaftStateMachine(
        MembershipRegistry(),
        PlacementRegistry(),
        NodeInventory(),
        store,
        AlertStore(),
    )
    yield sm
    store.close()


def test_apply_register_node(state_machine):
    entry = LogEntry(
        index=1,
        term=1,
        command=CommandType.REGISTER_NODE,
        payload={"node_id": "node1", "address": "node1:8001"},
    )
    state_machine.apply(entry)
    record = state_machine._membership.get_node("node1")
    assert record is not None
    assert record.address == "node1:8001"


def test_apply_allocate_block(state_machine):
    state_machine.apply(LogEntry(
        index=1, term=1, command=CommandType.REGISTER_NODE,
        payload={"node_id": "node1", "address": "n1:8001"},
    ))
    state_machine.apply(LogEntry(
        index=2, term=1, command=CommandType.ALLOCATE_BLOCK,
        payload={"block_id": "blk-1", "version": 1, "nodes": ["node1"]},
    ))
    assert state_machine._placement_registry.block_exists("blk-1")


def test_apply_add_alert(state_machine):
    state_machine.apply(LogEntry(
        index=1, term=1, command=CommandType.ADD_ALERT,
        payload={"severity": "CRITICAL", "node": "node1", "description": "disk full"},
    ))
    alerts = state_machine._alerts.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "CRITICAL"


def test_snapshot_roundtrip(state_machine):
    state_machine.apply(LogEntry(
        index=1, term=1, command=CommandType.REGISTER_NODE,
        payload={"node_id": "node1", "address": "n1:8001"},
    ))
    snap = state_machine.build_snapshot()
    fresh = RaftStateMachine(
        MembershipRegistry(),
        PlacementRegistry(),
        NodeInventory(),
        state_machine._store,
        AlertStore(),
    )
    fresh.restore_snapshot(snap)
    assert fresh._membership.get_node("node1") is not None
