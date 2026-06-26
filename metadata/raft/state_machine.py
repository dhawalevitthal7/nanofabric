"""Apply committed Raft commands to metadata state."""

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from metadata.models import NodeStatus
from metadata.raft.alert_store import AlertStore
from metadata.raft.models import CommandType, LogEntry

if TYPE_CHECKING:
    from cluster.repair_job_store import RepairJobStore
    from metadata.membership import MembershipRegistry
    from metadata.metadata_store import MetadataStore
    from metadata.node_inventory import NodeInventory
    from metadata.placement_registry import PlacementRegistry

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class RaftStateMachine:
    """Deterministic state machine for replicated metadata commands."""

    def __init__(
        self,
        membership: "MembershipRegistry",
        placement_registry: "PlacementRegistry",
        inventory: "NodeInventory",
        store: "MetadataStore",
        alert_store: AlertStore,
        repair_store: Optional["RepairJobStore"] = None,
    ) -> None:
        self._membership = membership
        self._placement_registry = placement_registry
        self._inventory = inventory
        self._store = store
        self._alerts = alert_store
        self._repair_store = repair_store
        self._peers: List[str] = []

    @property
    def peers(self) -> List[str]:
        return list(self._peers)

    def apply(self, entry: LogEntry) -> None:
        handler = {
            CommandType.REGISTER_NODE: self._apply_register,
            CommandType.UPDATE_HEARTBEAT: self._apply_heartbeat,
            CommandType.ALLOCATE_BLOCK: self._apply_allocate,
            CommandType.UPDATE_PLACEMENT: self._apply_placement,
            CommandType.CREATE_REPAIR: self._apply_create_repair,
            CommandType.DELETE_REPAIR: self._apply_delete_repair,
            CommandType.ADD_ALERT: self._apply_alert,
            CommandType.ADD_PEER: self._apply_add_peer,
            CommandType.REMOVE_PEER: self._apply_remove_peer,
            CommandType.RECONFIGURE_CLUSTER: self._apply_reconfigure,
        }.get(entry.command)
        if handler is None:
            log.warning("unknown command", extra={"command": entry.command})
            return
        handler(entry.payload)

    def _apply_register(self, payload: Dict[str, Any]) -> None:
        node_id = payload["node_id"]
        address = payload["address"]
        record = self._membership.register(node_id, address)
        self._store.upsert_node(node_id, status="UP", last_seen=record.last_seen)

    def _apply_heartbeat(self, payload: Dict[str, Any]) -> None:
        node_id = payload["node_id"]
        timestamp = payload.get("timestamp")
        try:
            record = self._membership.heartbeat(node_id, timestamp)
        except KeyError:
            return

        if (
            payload.get("block_count") is not None
            and payload.get("used_bytes") is not None
            and payload.get("last_lsn") is not None
        ):
            self._store.update_node_stats(
                node_id=node_id,
                block_count=payload["block_count"],
                used_bytes=payload["used_bytes"],
                last_lsn=payload["last_lsn"],
                last_seen=record.last_seen,
            )
        else:
            self._store.upsert_node(node_id, status="UP", last_seen=record.last_seen)

    def _apply_allocate(self, payload: Dict[str, Any]) -> None:
        block_id = payload["block_id"]
        version = payload.get("version", 1)
        nodes = payload["nodes"]
        self._store.save_placement(block_id, version, nodes)
        self._placement_registry.register_block(block_id, version, nodes)
        for node_id in nodes:
            self._inventory.add_block(node_id, block_id)

    def _apply_placement(self, payload: Dict[str, Any]) -> None:
        block_id = payload["block_id"]
        version = payload["version"]
        nodes = payload["nodes"]
        old = self._placement_registry.get_block_locations(block_id) or []
        self._store.save_placement(block_id, version, nodes)
        self._placement_registry.register_block(block_id, version, nodes)
        for node_id in old:
            if node_id not in nodes:
                self._inventory.remove_block(node_id, block_id)
        for node_id in nodes:
            if node_id not in old:
                self._inventory.add_block(node_id, block_id)

    def _apply_create_repair(self, payload: Dict[str, Any]) -> None:
        if self._repair_store is None:
            return
        from cluster.repair_models import RepairJob, RepairStatus, RepairType

        job = RepairJob(
            job_id=payload["job_id"],
            block_id=payload["block_id"],
            source_node=payload["source_node"],
            target_node=payload["target_node"],
            version=payload.get("version", 1),
            repair_type=RepairType(payload["repair_type"]),
            status=RepairStatus(payload.get("status", "PENDING")),
            attempt_count=payload.get("attempt_count", 0),
            last_error=payload.get("last_error"),
            created_at=payload.get("created_at", _now_ms()),
            updated_at=payload.get("updated_at", _now_ms()),
            completed_at=payload.get("completed_at"),
        )
        self._repair_store.upsert_job(job)

    def _apply_delete_repair(self, payload: Dict[str, Any]) -> None:
        if self._repair_store is None:
            return
        self._repair_store.delete_job(payload["job_id"])

    def _apply_alert(self, payload: Dict[str, Any]) -> None:
        self._alerts.add_alert(
            severity=payload["severity"],
            node=payload["node"],
            description=payload["description"],
            alert_id=payload.get("alert_id"),
        )

    def _apply_add_peer(self, payload: Dict[str, Any]) -> None:
        peer = payload["peer_id"]
        if peer not in self._peers:
            self._peers.append(peer)

    def _apply_remove_peer(self, payload: Dict[str, Any]) -> None:
        peer = payload["peer_id"]
        if peer in self._peers:
            self._peers.remove(peer)

    def _apply_reconfigure(self, payload: Dict[str, Any]) -> None:
        self._peers = list(payload.get("peers", []))

    def build_snapshot(self) -> dict:
        nodes = {
            nid: rec.model_dump()
            for nid, rec in self._membership.get_all_nodes().items()
        }
        placements = self._placement_registry.list_all_blocks()
        versions = {
            bid: self._placement_registry.get_block_version(bid) or 1
            for bid in placements
        }
        inventory = {
            node_id: self._inventory.get_inventory(node_id)
            for node_id in nodes
        }
        repairs: List[dict] = []
        if self._repair_store is not None:
            repairs = [j.model_dump() for j in self._repair_store.list_all_jobs()]

        return {
            "nodes": nodes,
            "placements": placements,
            "versions": versions,
            "inventory": inventory,
            "alerts": self._alerts.to_snapshot(),
            "repairs": repairs,
            "peers": self._peers,
        }

    def restore_snapshot(self, data: dict) -> None:
        from metadata.models import NodeRecord

        with self._membership._lock:
            self._membership._nodes = {
                nid: NodeRecord(**rec) for nid, rec in data.get("nodes", {}).items()
            }

        self._placement_registry.load_from_snapshot(
            data.get("placements", {}),
            data.get("versions", {}),
        )
        for node_id, blocks in data.get("inventory", {}).items():
            self._inventory.register_inventory(node_id, blocks)

        self._alerts.load_snapshot(data.get("alerts", []))
        self._peers = list(data.get("peers", []))

        if self._repair_store is not None:
            for job_data in data.get("repairs", []):
                from cluster.repair_models import RepairJob, RepairStatus, RepairType

                job = RepairJob(
                    job_id=job_data["job_id"],
                    block_id=job_data["block_id"],
                    source_node=job_data["source_node"],
                    target_node=job_data["target_node"],
                    version=job_data["version"],
                    repair_type=RepairType(job_data["repair_type"]),
                    status=RepairStatus(job_data["status"]),
                    attempt_count=job_data["attempt_count"],
                    last_error=job_data.get("last_error"),
                    created_at=job_data["created_at"],
                    updated_at=job_data["updated_at"],
                    completed_at=job_data.get("completed_at"),
                )
                self._repair_store.upsert_job(job)

        log.info("state machine restored from snapshot")
