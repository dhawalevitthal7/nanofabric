"""Tests for Merkle-based anti-entropy."""

import pytest

from cluster.anti_entropy_service import AntiEntropyService
from cluster.re_replication_service import ReReplicationService
from metadata.app import get_placement_service, get_registry
from metadata.placement_policy import RoundRobinPlacementPolicy
from replication_helpers import RoutingNodeClient, RoutingReplicaClient


@pytest.fixture
def anti_entropy(repair_cluster):
    metadata_tc, node_clients, _, routing_client, routing_node = repair_cluster
    placement = get_placement_service()
    registry = get_registry()
    policy = RoundRobinPlacementPolicy()

    def select_replacement(block_id, current_nodes, healthy_nodes):
        available = [n for n in healthy_nodes if n not in current_nodes]
        return policy.select_nodes(available, 1)[0] if available else None

    re_rep = ReReplicationService(
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

    svc = AntiEntropyService(
        list_placements_fn=placement.list_all_placements,
        get_healthy_nodes_fn=placement.get_healthy_nodes,
        get_node_addresses_fn=lambda: {
            nid: rec.address for nid, rec in registry.get_all_nodes().items()
        },
        re_replication=re_rep,
        node_client=routing_node,
    )
    return svc, metadata_tc, node_clients


def test_compare_replicas_no_divergence(anti_entropy):
    svc, metadata, nodes = anti_entropy
    metadata.post("/allocate", json={"block_id": "sync-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "sync-blk", "data": "same", "version": 1})

    result = svc.compare_replicas("sync-blk")
    assert result is None


def test_verify_cluster(anti_entropy):
    svc, metadata, nodes = anti_entropy
    metadata.post("/allocate", json={"block_id": "cluster-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "cluster-blk", "data": "d", "version": 1})

    report = svc.verify_cluster()
    assert "healthy" in report
    assert "diverged_blocks" in report


def test_repair_divergence(anti_entropy):
    svc, metadata, nodes = anti_entropy
    metadata.post("/allocate", json={"block_id": "div-blk", "rf": 3})
    nodes["node1"].post("/write", json={"block_id": "div-blk", "data": "v1", "version": 1})
    nodes["node1"].app.state.engine.write_local("div-blk", "v2-newer", 2)

    result = svc.repair_divergence("div-blk")
    assert result["ok"] is True
