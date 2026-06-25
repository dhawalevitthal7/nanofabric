"""Tests for re-replication service."""

import pytest

from cluster.re_replication_service import ReReplicationService
from metadata.app import get_placement_service, get_registry
from metadata.placement_policy import RoundRobinPlacementPolicy
from replication_helpers import RoutingNodeClient, RoutingReplicaClient


@pytest.fixture
def re_replication(repair_cluster):
    metadata_tc, node_clients, metadata_client, routing_client, routing_node = repair_cluster
    placement = get_placement_service()
    registry = get_registry()
    policy = RoundRobinPlacementPolicy()

    def select_replacement(block_id, current_nodes, healthy_nodes):
        available = [n for n in healthy_nodes if n not in current_nodes]
        return policy.select_nodes(available, 1)[0] if available else None

    svc = ReReplicationService(
        node_id="metadata",
        replica_client=routing_client,
        node_client=routing_node,
        get_node_addresses_fn=lambda: {
            nid: rec.address for nid, rec in registry.get_all_nodes().items()
        },
        get_block_locations_fn=placement.get_block_locations,
        replace_replica_fn=placement.replace_replica,
        select_replacement_fn=select_replacement,
        get_healthy_nodes_fn=placement.get_healthy_nodes,
    )
    return svc, metadata_tc, node_clients, placement


def test_copy_block_between_nodes(re_replication):
    svc, metadata, nodes, _ = re_replication
    metadata.post("/allocate", json={"block_id": "copy-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "copy-blk", "data": "payload", "version": 1})

    addresses = {f"node{i}": f"node{i}:800{i}" for i in range(1, 5)}
    ok = svc.copy_block("copy-blk", "node1", "node4", 1, addresses)
    assert ok is True

    record = nodes["node4"].get("/read/copy-blk").json()
    assert record["data"] == "payload"


def test_verify_copy(re_replication):
    svc, metadata, nodes, _ = re_replication
    metadata.post("/allocate", json={"block_id": "verify-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "verify-blk", "data": "same", "version": 1})

    addresses = {f"node{i}": f"node{i}:800{i}" for i in range(1, 5)}
    svc.copy_block("verify-blk", "node1", "node2", 1, addresses)
    assert svc.verify_copy("verify-blk", "node1", "node2", addresses) is True


def test_repair_block_updates_metadata(re_replication):
    svc, metadata, nodes, placement = re_replication
    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
    nodes["node1"].post(
        "/write", json={"block_id": "invoice-123", "data": "invoice", "version": 1}
    )

    result = svc.repair_block("invoice-123", version=1)
    assert result["ok"] is True

    locations = metadata.get("/blocks/invoice-123").json()["locations"]
    assert "node4" in locations or len([n for n in locations if n != "node3"]) == 3
