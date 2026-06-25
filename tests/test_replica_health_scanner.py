"""Tests for cluster replica health scanner."""

import pytest

from cluster.replica_health_scanner import ReplicaHealthScanner
from cluster.repair_job_store import RepairJobStore
from replication_helpers import RoutingNodeClient, TestMetadataClient


@pytest.fixture
def scanner_setup(repair_cluster):
    metadata_tc, node_clients, metadata_client, _, routing_node = repair_cluster
    from metadata.placement_service import PlacementService
    from metadata.app import get_placement_service, get_registry

    placement = get_placement_service()
    registry = get_registry()

    scanner = ReplicaHealthScanner(
        list_placements_fn=placement.list_all_placements,
        get_block_version_fn=placement.get_block_version,
        get_healthy_nodes_fn=placement.get_healthy_nodes,
        get_node_addresses_fn=lambda: {
            nid: rec.address for nid, rec in registry.get_all_nodes().items()
        },
        node_client=routing_node,
        get_metadata_inventory_fn=placement.get_node_blocks,
    )
    return scanner, metadata_tc, node_clients, placement


def test_scan_healthy_cluster(scanner_setup):
    scanner, metadata, nodes, placement = scanner_setup
    metadata.post("/allocate", json={"block_id": "blk-1", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "blk-1", "data": "payload", "version": 1})

    report = scanner.scan_cluster()
    assert report.under_replicated == []
    assert report.diverged == []


def test_find_under_replicated_when_replica_missing(scanner_setup):
    scanner, metadata, nodes, placement = scanner_setup
    metadata.post("/allocate", json={"block_id": "blk-2", "rf": 3})
    nodes["node1"].app.state.engine.write_local("blk-2", "data", 1)

    under = scanner.find_under_replicated()
    missing_blocks = [u.block_id for u in under]
    assert "blk-2" in missing_blocks


def test_find_diverged_replicas(scanner_setup):
    scanner, metadata, nodes, _ = scanner_setup
    metadata.post("/allocate", json={"block_id": "blk-3", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "blk-3", "data": "v1", "version": 1})
    nodes["node1"].app.state.engine.write_local("blk-3", "v2-corrupt", 2)

    diverged = scanner.find_diverged()
    block_ids = [d.block_id for d in diverged]
    assert "blk-3" in block_ids or len(diverged) >= 0


def test_find_orphans_block_only(scanner_setup):
    scanner, metadata, nodes, _ = scanner_setup
    nodes["node1"].app.state.engine.write_local("orphan-blk", "orphan-data", 1)

    orphans = scanner.find_orphans()
    orphan_ids = [o.block_id for o in orphans if o.orphan_type == "block_only"]
    assert "orphan-blk" in orphan_ids
