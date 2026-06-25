"""Tests for the placement service orchestration."""

import pytest

from metadata.membership import MembershipRegistry
from metadata.metadata_store import MetadataStore
from metadata.node_inventory import NodeInventory
from metadata.placement_policy import RoundRobinPlacementPolicy
from metadata.placement_registry import PlacementRegistry
from metadata.placement_service import (
    BlockAlreadyExistsError,
    InsufficientNodesError,
    PlacementService,
)


@pytest.fixture
def service(tmp_path):
    store = MetadataStore(tmp_path / "metadata.db")
    registry = MembershipRegistry()
    placement_registry = PlacementRegistry()
    inventory = NodeInventory()
    policy = RoundRobinPlacementPolicy()
    svc = PlacementService(
        registry=registry,
        placement_registry=placement_registry,
        inventory=inventory,
        store=store,
        policy=policy,
    )
    for node_id in ("node1", "node2", "node3"):
        registry.register(node_id, f"{node_id}:8000")
    yield svc
    store.close()


def test_allocate_block_round_robin(service):
    nodes = service.allocate_block("invoice-1", rf=1)
    assert nodes == ["node1"]

    nodes2 = service.allocate_block("invoice-2", rf=1)
    assert nodes2 == ["node2"]

    assert service.get_block_locations("invoice-1") == ["node1"]
    assert service.get_node_blocks("node1") == ["invoice-1"]


def test_allocate_rf2(service):
    nodes = service.allocate_block("invoice-123", rf=2)
    assert nodes == ["node1", "node2"]
    assert service.get_block_locations("invoice-123") == ["node1", "node2"]
    assert "invoice-123" in service.get_node_blocks("node1")
    assert "invoice-123" in service.get_node_blocks("node2")


def test_allocate_persists_across_restart(tmp_path):
    db_path = tmp_path / "metadata.db"
    registry = MembershipRegistry()
    for node_id in ("node1", "node2", "node3"):
        registry.register(node_id, f"{node_id}:8000")

    store = MetadataStore(db_path)
    svc = PlacementService(
        registry=registry,
        placement_registry=PlacementRegistry(),
        inventory=NodeInventory(),
        store=store,
        policy=RoundRobinPlacementPolicy(),
    )
    svc.allocate_block("invoice-123", rf=2)
    store.close()

    store2 = MetadataStore(db_path)
    placement_registry = PlacementRegistry()
    inventory = NodeInventory()
    policy = RoundRobinPlacementPolicy()
    svc2 = PlacementService(
        registry=registry,
        placement_registry=placement_registry,
        inventory=inventory,
        store=store2,
        policy=policy,
    )
    svc2.recover()

    assert svc2.get_block_locations("invoice-123") == ["node1", "node2"]
    assert svc2.get_node_blocks("node1") == ["invoice-123"]
    store2.close()


def test_duplicate_allocation_raises(service):
    service.allocate_block("invoice-1", rf=1)
    with pytest.raises(BlockAlreadyExistsError):
        service.allocate_block("invoice-1", rf=1)


def test_insufficient_nodes(service):
    for node_id in ("node1", "node2", "node3"):
        service._membership.heartbeat(node_id, timestamp=1000)
    service._membership.check_failures(now_ms=10_000)
    with pytest.raises(InsufficientNodesError):
        service.allocate_block("invoice-x", rf=1)


def test_delete_block(service):
    service.allocate_block("invoice-1", rf=2)
    assert service.delete_block("invoice-1") is True
    assert service.get_block_locations("invoice-1") is None
    assert service.get_node_blocks("node1") == []
