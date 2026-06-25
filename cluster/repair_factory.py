"""Factory for wiring cluster repair components on the metadata service."""

from pathlib import Path
from typing import Callable, Dict, Optional

from cluster.anti_entropy_service import AntiEntropyService
from cluster.node_client import NodeClient
from cluster.placement_reconciliation import PlacementReconciliation
from cluster.re_replication_service import ReReplicationService
from cluster.repair_job_store import RepairJobStore
from cluster.repair_metrics import RepairMetrics
from cluster.repair_service import RepairService
from cluster.replica_health_scanner import ReplicaHealthScanner
from metadata.membership import MembershipRegistry
from metadata.placement_policy import PlacementPolicy
from metadata.placement_service import PlacementService
from node.replica_client import ReplicaClient


def build_repair_stack(
    placement_service: PlacementService,
    membership: MembershipRegistry,
    placement_policy: PlacementPolicy,
    db_path: str | Path,
    coordinator_node_id: str = "metadata",
    replica_client: Optional[ReplicaClient] = None,
    node_client: Optional[NodeClient] = None,
    metrics: Optional[RepairMetrics] = None,
) -> RepairService:
    """Wire all Phase 6 repair components and return the orchestrator."""
    metrics = metrics or RepairMetrics()
    job_store = RepairJobStore(db_path)
    node_client = node_client or NodeClient()
    replica_client = replica_client or ReplicaClient()

    def get_addresses() -> Dict[str, str]:
        nodes = membership.get_all_nodes()
        return {nid: rec.address for nid, rec in nodes.items()}

    def select_replacement(
        block_id: str,
        current_nodes: list,
        healthy_nodes: list,
    ) -> Optional[str]:
        available = [n for n in healthy_nodes if n not in current_nodes]
        if not available:
            return None
        return placement_policy.select_nodes(available, 1)[0]

    re_replication = ReReplicationService(
        node_id=coordinator_node_id,
        replica_client=replica_client,
        node_client=node_client,
        get_node_addresses_fn=get_addresses,
        get_block_locations_fn=placement_service.get_block_locations,
        replace_replica_fn=placement_service.replace_replica,
        select_replacement_fn=select_replacement,
        get_healthy_nodes_fn=placement_service.get_healthy_nodes,
        metrics=metrics,
    )

    health_scanner = ReplicaHealthScanner(
        list_placements_fn=placement_service.list_all_placements,
        get_block_version_fn=placement_service.get_block_version,
        get_healthy_nodes_fn=placement_service.get_healthy_nodes,
        get_node_addresses_fn=get_addresses,
        node_client=node_client,
        get_metadata_inventory_fn=placement_service.get_node_blocks,
    )

    placement_reconciliation = PlacementReconciliation(
        list_placements_fn=placement_service.list_all_placements,
        get_node_inventory_fn=placement_service.get_node_blocks,
        update_placement_fn=placement_service.update_block_placement,
        rebuild_inventory_fn=placement_service.rebuild_node_inventory,
        get_node_addresses_fn=get_addresses,
        get_block_version_fn=placement_service.get_block_version,
        node_client=node_client,
    )

    anti_entropy = AntiEntropyService(
        list_placements_fn=placement_service.list_all_placements,
        get_healthy_nodes_fn=placement_service.get_healthy_nodes,
        get_node_addresses_fn=get_addresses,
        re_replication=re_replication,
        node_client=node_client,
        metrics=metrics,
    )

    return RepairService(
        coordinator_node_id=coordinator_node_id,
        job_store=job_store,
        health_scanner=health_scanner,
        re_replication=re_replication,
        anti_entropy=anti_entropy,
        placement_reconciliation=placement_reconciliation,
        placement_policy=placement_policy,
        get_healthy_nodes_fn=placement_service.get_healthy_nodes,
        get_block_version_fn=placement_service.get_block_version,
        remove_extra_replica_fn=placement_service.remove_extra_replica,
        metrics=metrics,
    )
