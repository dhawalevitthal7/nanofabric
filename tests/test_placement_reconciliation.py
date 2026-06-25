"""Tests for placement metadata reconciliation."""

import pytest

from cluster.placement_reconciliation import PlacementReconciliation
from metadata.app import get_placement_service, get_registry
from replication_helpers import RoutingNodeClient


@pytest.fixture
def reconciliation(repair_cluster):
    metadata_tc, node_clients, _, _, routing_node = repair_cluster
    placement = get_placement_service()
    registry = get_registry()

    svc = PlacementReconciliation(
        list_placements_fn=placement.list_all_placements,
        get_node_inventory_fn=placement.get_node_blocks,
        update_placement_fn=placement.update_block_placement,
        rebuild_inventory_fn=placement.rebuild_node_inventory,
        get_node_addresses_fn=lambda: {
            nid: rec.address for nid, rec in registry.get_all_nodes().items()
        },
        get_block_version_fn=placement.get_block_version,
        node_client=routing_node,
    )
    return svc, metadata_tc, node_clients, placement


def test_detect_metadata_only_orphan(reconciliation):
    svc, metadata, nodes, placement = reconciliation
    metadata.post("/allocate", json={"block_id": "meta-only", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "meta-only", "data": "d", "version": 1})

    mismatches = svc.detect_mismatches()
    assert "metadata_only" in mismatches
    assert "block_only" in mismatches


def test_detect_block_only_orphan(reconciliation):
    svc, metadata, nodes, placement = reconciliation
    nodes["node1"].app.state.engine.write_local("orphan-only", "data", 1)

    mismatches = svc.detect_mismatches()
    block_only = [o.block_id for o in mismatches["block_only"]]
    assert "orphan-only" in block_only


def test_reconcile_rebuilds_inventory(reconciliation):
    svc, metadata, nodes, placement = reconciliation
    nodes["node1"].app.state.engine.write_local("recon-blk", "data", 1)

    result = svc.reconcile()
    assert "cleaned_orphans" in result
    assert result["block_only"] >= 1
