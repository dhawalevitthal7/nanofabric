"""FastAPI metadata service — cluster brain for membership, health, and placement."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from cluster.repair_factory import build_repair_stack
from cluster.repair_metrics import RepairMetrics
from cluster.repair_worker import RepairWorker
from metadata.failure_detector import FailureDetector
from metadata.membership import MembershipRegistry
from metadata.metadata_store import MetadataStore
from metadata.models import (
    AllocateRequest,
    AllocateResponse,
    BlockLocationsResponse,
    HeartbeatRequest,
    MetadataStatsResponse,
    NodeRecord,
    RegisterRequest,
)
from metadata.node_inventory import NodeInventory
from metadata.placement_policy import RoundRobinPlacementPolicy
from metadata.placement_registry import PlacementRegistry
from metadata.placement_service import (
    BlockAlreadyExistsError,
    InsufficientNodesError,
    PlacementService,
)
from metadata.raft.alert_store import AlertStore
from metadata.raft.config import RaftConfig, load_raft_config
from metadata.raft.metrics import RaftMetrics
from metadata.raft.models import (
    AppendEntriesRequest,
    AppendEntriesResponse,
    CommandType,
    RaftLeaderResponse,
    RaftStatusResponse,
    RequestVoteRequest,
    RequestVoteResponse,
)
from metadata.raft.node import RaftNode
from metadata.raft.state_machine import RaftStateMachine
from metadata.raft.storage import RaftStorage
from storage.models import BackupType, PolicySchedule
from storage.protection_factory import build_protection_stack
from storage.cluster_bridge import ClusterBlockBridge, make_placement_restore
from cluster.node_client import NodeClient

log = logging.getLogger(__name__)

_registry: Optional[MembershipRegistry] = None
_detector: Optional[FailureDetector] = None
_store: Optional[MetadataStore] = None
_placement_registry: Optional[PlacementRegistry] = None
_inventory: Optional[NodeInventory] = None
_placement_service: Optional[PlacementService] = None
_placement_policy: Optional[RoundRobinPlacementPolicy] = None
_repair_service = None
_repair_worker: Optional[RepairWorker] = None
_repair_metrics: Optional[RepairMetrics] = None
_raft_node: Optional[RaftNode] = None
_raft_metrics: Optional[RaftMetrics] = None
_alert_store: Optional[AlertStore] = None
_raft_config: Optional[RaftConfig] = None
_protection_stack = None


class RepairBlockRequest(BaseModel):
    block_id: str = Field(..., min_length=1)


class RepairNodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1)


def get_registry() -> MembershipRegistry:
    if _registry is None:
        raise RuntimeError("Membership registry is not initialized")
    return _registry


def get_placement_service() -> PlacementService:
    if _placement_service is None:
        raise RuntimeError("Placement service is not initialized")
    return _placement_service


def get_repair_service():
    if _repair_service is None:
        raise RuntimeError("Repair service is not initialized")
    return _repair_service


def get_store() -> MetadataStore:
    if _store is None:
        raise RuntimeError("Metadata store is not initialized")
    return _store


def get_raft_node() -> Optional[RaftNode]:
    return _raft_node


def get_protection_stack():
    if _protection_stack is None:
        raise RuntimeError("Protection stack is not initialized")
    return _protection_stack


def get_alert_store() -> AlertStore:
    if _alert_store is None:
        raise RuntimeError("Alert store is not initialized")
    return _alert_store


def _raft_enabled() -> bool:
    return _raft_node is not None


def _leader_redirect():
    if _raft_node is None or _raft_node.is_leader():
        return None
    url = _raft_node.leader_url()
    if url:
        return RedirectResponse(url=url, status_code=307)
    raise HTTPException(status_code=503, detail="No Raft leader available")


def _propose_or_raise(command: CommandType, payload: dict) -> None:
    if _raft_node is None:
        return
    result = _raft_node.propose(command, payload)
    if not result.success:
        if result.error == "not leader":
            redirect = _leader_redirect()
            if redirect:
                raise HTTPException(status_code=307, headers={"Location": _raft_node.leader_url() or ""})
        raise HTTPException(status_code=503, detail=result.error or "raft propose failed")


def _default_db_path() -> Path:
    return Path(os.environ.get("METADATA_DB_PATH", "metadata.db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _detector, _store, _placement_registry, _inventory
    global _placement_service, _placement_policy, _repair_service, _repair_worker, _repair_metrics
    global _raft_node, _raft_metrics, _alert_store, _raft_config, _protection_stack

    db_path = app.state.db_path if hasattr(app.state, "db_path") else _default_db_path()
    _store = MetadataStore(db_path)
    _registry = MembershipRegistry()
    _placement_registry = PlacementRegistry()
    _inventory = NodeInventory()
    _placement_policy = RoundRobinPlacementPolicy()
    _alert_store = AlertStore()
    _placement_service = PlacementService(
        registry=_registry,
        placement_registry=_placement_registry,
        inventory=_inventory,
        store=_store,
        policy=_placement_policy,
    )
    _placement_service.recover()
    _detector = FailureDetector(_registry)
    _detector.start()

    repair_db = db_path.parent / "repair.db"
    _repair_metrics = RepairMetrics()
    _repair_service = build_repair_stack(
        placement_service=_placement_service,
        membership=_registry,
        placement_policy=_placement_policy,
        db_path=repair_db,
        metrics=_repair_metrics,
        replica_client=app.state.replica_client if hasattr(app.state, "replica_client") else None,
        node_client=app.state.node_client if hasattr(app.state, "node_client") else None,
    )

    _raft_config = getattr(app.state, "raft_config", None) or load_raft_config()
    if _raft_config and _raft_config.enabled:
        raft_db = db_path.parent / "raft.db"
        raft_storage = RaftStorage(raft_db)
        _raft_metrics = RaftMetrics()
        state_machine = RaftStateMachine(
            membership=_registry,
            placement_registry=_placement_registry,
            inventory=_inventory,
            store=_store,
            alert_store=_alert_store,
            repair_store=_repair_service._job_store,
        )
        peer_urls = dict(_raft_config.peer_urls)
        if _raft_config.advertise_url:
            peer_urls[_raft_config.node_id] = _raft_config.advertise_url

        _raft_node = RaftNode(
            node_id=_raft_config.node_id,
            peer_urls=peer_urls,
            storage=raft_storage,
            state_machine=state_machine,
            metrics=_raft_metrics,
            election_min_ms=_raft_config.election_min_ms,
            election_max_ms=_raft_config.election_max_ms,
            snapshot_threshold=_raft_config.snapshot_threshold,
            rpc_client=getattr(app.state, "raft_rpc_client", None),
        )
        _raft_node.start()
        log.info(
            "raft cluster enabled",
            extra={"node_id": _raft_config.node_id, "peers": list(peer_urls.keys())},
        )

    start_repair_worker = getattr(app.state, "start_repair_worker", True)
    if start_repair_worker:
        _repair_worker = RepairWorker(_repair_service)
        _repair_worker.start()

    protection_dir = db_path.parent / "protection"
    node_client = app.state.node_client if hasattr(app.state, "node_client") else NodeClient()

    def get_addresses():
        nodes = _registry.get_all_nodes()
        return {nid: rec.address for nid, rec in nodes.items()}

    block_bridge = getattr(app.state, "block_bridge", None) or ClusterBlockBridge(
        node_client=node_client,
        get_addresses=get_addresses,
        get_placements=lambda: _placement_service.list_all_placements(),
        placement_service=_placement_service,
    )
    restore_placement = make_placement_restore(_store, _placement_registry)
    start_protection_scheduler = getattr(app.state, "start_protection_scheduler", False)
    _protection_stack = getattr(app.state, "protection_stack", None) or build_protection_stack(
        data_dir=protection_dir,
        read_blocks=block_bridge,
        write_blocks=block_bridge,
        get_metadata_version=lambda: _store.get_stats()["total_blocks"],
        get_placements=lambda: _placement_service.list_all_placements(),
        restore_placement=restore_placement,
        start_scheduler=start_protection_scheduler,
    )

    log.info("metadata service started", extra={"db_path": str(db_path)})
    yield
    if _raft_node:
        _raft_node.stop()
    if _repair_worker:
        _repair_worker.stop()
    if _detector:
        _detector.stop()
    if _repair_service is not None:
        _repair_service._job_store.close()
    if _protection_stack:
        _protection_stack.close()
    if _store:
        _store.close()
    _raft_node = None
    _raft_metrics = None
    _alert_store = None
    _raft_config = None
    _protection_stack = None
    _repair_worker = None
    _repair_service = None
    _repair_metrics = None
    _detector = None
    _placement_service = None
    _placement_policy = None
    _inventory = None
    _placement_registry = None
    _store = None
    _registry = None
    log.info("metadata service stopped")


def create_app(db_path: Optional[str | Path] = None, raft_config: Optional[RaftConfig] = None) -> FastAPI:
    app = FastAPI(title="NanoFabric Metadata Service", lifespan=lifespan)
    if db_path is not None:
        app.state.db_path = Path(db_path)
    if raft_config is not None:
        app.state.raft_config = raft_config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.websocket("/ws/cluster")
    async def ws_cluster(websocket: WebSocket):
        from metadata.realtime import websocket_cluster
        await websocket_cluster(websocket, app)

    @app.get("/events/stream")
    async def events_stream():
        from metadata.realtime import sse_stream
        return await sse_stream(app)

    @app.get("/health")
    def health():
        registry = get_registry()
        summary = registry.get_cluster_summary()
        up_count = sum(1 for status in summary.values() if status == "UP")
        body = {
            "status": "ok",
            "nodes_total": len(summary),
            "nodes_up": up_count,
            "nodes_down": len(summary) - up_count,
        }
        if _raft_node:
            body["raft"] = _raft_node.get_status()
        return body

    @app.post("/raft/request-vote", response_model=RequestVoteResponse)
    def raft_request_vote(request: RequestVoteRequest):
        if _raft_node is None:
            raise HTTPException(status_code=404, detail="Raft not enabled")
        return _raft_node.handle_request_vote(request)

    @app.post("/raft/append-entries", response_model=AppendEntriesResponse)
    def raft_append_entries(request: AppendEntriesRequest):
        if _raft_node is None:
            raise HTTPException(status_code=404, detail="Raft not enabled")
        return _raft_node.handle_append_entries(request)

    @app.get("/raft/status", response_model=RaftStatusResponse)
    def raft_status():
        if _raft_node is None:
            raise HTTPException(status_code=404, detail="Raft not enabled")
        return RaftStatusResponse(**_raft_node.get_status())

    @app.get("/raft/leader", response_model=RaftLeaderResponse)
    def raft_leader():
        if _raft_node is None:
            raise HTTPException(status_code=404, detail="Raft not enabled")
        status = _raft_node.get_status()
        return RaftLeaderResponse(
            leader=status["leader"],
            term=status["term"],
            role=status["role"],
            leader_url=_raft_node.leader_url(),
        )

    @app.get("/raft/metrics")
    def raft_metrics():
        if _raft_metrics is None:
            raise HTTPException(status_code=404, detail="Raft not enabled")
        return _raft_metrics.get_snapshot()

    @app.get("/raft/alerts")
    def raft_alerts():
        return get_alert_store().list_alerts()

    class ReconfigureRequest(BaseModel):
        peers: list[str]
        peer_urls: dict[str, str] = Field(default_factory=dict)

    @app.post("/raft/reconfigure")
    def raft_reconfigure(body: ReconfigureRequest):
        redirect = _leader_redirect()
        if redirect:
            return redirect
        peer_urls = body.peer_urls or {
            pid: f"http://localhost:900{int(pid[-1])}" for pid in body.peers
        }
        result = _raft_node.propose(
            CommandType.RECONFIGURE_CLUSTER,
            {"peers": body.peers, "peer_urls": peer_urls},
        )
        if not result.success:
            raise HTTPException(status_code=503, detail=result.error)
        _raft_node.reconfigure_peers(peer_urls)
        return {"peers": body.peers, "committed": True}

    @app.post("/raft/peers/add")
    def raft_add_peer(peer_id: str, peer_url: str):
        redirect = _leader_redirect()
        if redirect:
            return redirect
        result = _raft_node.propose(CommandType.ADD_PEER, {"peer_id": peer_id, "peer_url": peer_url})
        if not result.success:
            raise HTTPException(status_code=503, detail=result.error)
        urls = dict(_raft_node.peer_urls)
        urls[peer_id] = peer_url
        _raft_node.reconfigure_peers(urls)
        return {"peer_id": peer_id, "added": True}

    @app.post("/raft/peers/remove")
    def raft_remove_peer(peer_id: str):
        redirect = _leader_redirect()
        if redirect:
            return redirect
        result = _raft_node.propose(CommandType.REMOVE_PEER, {"peer_id": peer_id})
        if not result.success:
            raise HTTPException(status_code=503, detail=result.error)
        urls = {k: v for k, v in _raft_node.peer_urls.items() if k != peer_id}
        _raft_node.reconfigure_peers(urls)
        return {"peer_id": peer_id, "removed": True}

    @app.post("/register", response_model=NodeRecord)
    def register(request: RegisterRequest):
        redirect = _leader_redirect()
        if redirect:
            return redirect

        if _raft_enabled():
            _propose_or_raise(
                CommandType.REGISTER_NODE,
                {"node_id": request.node_id, "address": request.address},
            )
            record = get_registry().get_node(request.node_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Node '{request.node_id}' not found")
            return record

        record = get_registry().register(request.node_id, request.address)
        get_store().upsert_node(request.node_id, status="UP", last_seen=record.last_seen)
        return record

    @app.post("/heartbeat", response_model=NodeRecord)
    def heartbeat(request: HeartbeatRequest):
        redirect = _leader_redirect()
        if redirect:
            return redirect

        if _raft_enabled():
            payload = {
                "node_id": request.node_id,
                "timestamp": request.timestamp,
                "block_count": request.block_count,
                "used_bytes": request.used_bytes,
                "last_lsn": request.last_lsn,
            }
            _propose_or_raise(CommandType.UPDATE_HEARTBEAT, payload)
            record = get_registry().get_node(request.node_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Node '{request.node_id}' is not registered")
            return record

        try:
            record = get_registry().heartbeat(request.node_id, request.timestamp)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if (
            request.block_count is not None
            and request.used_bytes is not None
            and request.last_lsn is not None
        ):
            get_store().update_node_stats(
                node_id=request.node_id,
                block_count=request.block_count,
                used_bytes=request.used_bytes,
                last_lsn=request.last_lsn,
                last_seen=record.last_seen,
            )
        else:
            get_store().upsert_node(
                request.node_id,
                status="UP",
                last_seen=record.last_seen,
            )
        return record

    @app.get("/nodes")
    def list_nodes():
        nodes = get_registry().get_all_nodes()
        return {node_id: record.model_dump() for node_id, record in nodes.items()}

    @app.get("/cluster-summary")
    def cluster_summary():
        return get_registry().get_cluster_summary()

    @app.post("/allocate", response_model=AllocateResponse)
    def allocate(request: AllocateRequest):
        redirect = _leader_redirect()
        if redirect:
            return redirect

        try:
            if _raft_enabled():
                service = get_placement_service()
                if service._placement_registry.block_exists(request.block_id):
                    raise BlockAlreadyExistsError(f"Block '{request.block_id}' already allocated")
                healthy = service.get_healthy_nodes()
                if len(healthy) < request.rf:
                    raise InsufficientNodesError(
                        f"Need {request.rf} healthy nodes but only {len(healthy)} available"
                    )
                nodes = service._policy.select_nodes(healthy, request.rf)
                _propose_or_raise(
                    CommandType.ALLOCATE_BLOCK,
                    {"block_id": request.block_id, "rf": request.rf, "version": 1, "nodes": nodes},
                )
                return AllocateResponse(nodes=nodes)

            nodes = get_placement_service().allocate_block(
                block_id=request.block_id,
                rf=request.rf,
            )
            return AllocateResponse(nodes=nodes)
        except BlockAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InsufficientNodesError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/blocks/{block_id}", response_model=BlockLocationsResponse)
    def get_block_locations(block_id: str):
        locations = get_placement_service().get_block_locations(block_id)
        if locations is None:
            raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
        return BlockLocationsResponse(locations=locations)

    @app.get("/placements")
    def list_placements():
        return get_placement_service().list_all_placements()

    @app.get("/nodes/{node_id}/blocks")
    def get_node_blocks(node_id: str):
        blocks = get_placement_service().get_node_blocks(node_id)
        return {"node_id": node_id, "blocks": blocks}

    @app.get("/metadata/stats", response_model=MetadataStatsResponse)
    def metadata_stats():
        stats = get_placement_service().get_metadata_stats()
        return MetadataStatsResponse(**stats)

    @app.get("/repairs")
    def list_repairs():
        jobs = get_repair_service()._job_store.list_all_jobs()
        return [job.model_dump() for job in jobs]

    @app.get("/repairs/pending")
    def list_pending_repairs():
        from cluster.repair_models import RepairStatus
        jobs = get_repair_service()._job_store.list_jobs_by_status(RepairStatus.PENDING)
        return [job.model_dump() for job in jobs]

    @app.get("/repairs/failed")
    def list_failed_repairs():
        from cluster.repair_models import RepairStatus
        jobs = get_repair_service()._job_store.list_jobs_by_status(RepairStatus.FAILED)
        return [job.model_dump() for job in jobs]

    @app.get("/cluster/health")
    def cluster_health():
        return get_repair_service().get_cluster_health()

    @app.get("/cluster/integrity")
    def cluster_integrity():
        return get_repair_service().get_cluster_integrity()

    @app.post("/repairs/run")
    def run_repairs():
        return get_repair_service().run_repair_cycle()

    @app.post("/repairs/rebuild")
    def rebuild_repairs(body: RepairBlockRequest):
        return get_repair_service().repair_block(body.block_id)

    @app.post("/repairs/verify")
    def verify_repairs():
        report = get_repair_service().scan_cluster()
        return {
            "under_replicated": len(report.under_replicated),
            "over_replicated": len(report.over_replicated),
            "diverged": len(report.diverged),
            "orphans": len(report.orphans),
        }

    @app.post("/repairs/reconcile")
    def reconcile_repairs():
        return get_repair_service().reconcile_placements()

    @app.post("/repairs/node")
    def repair_node(body: RepairNodeRequest):
        return get_repair_service().repair_node(body.node_id)

    class BackupCreateRequest(BaseModel):
        backup_type: BackupType = BackupType.FULL
        base_backup_id: Optional[str] = None

    class SnapshotPolicyRequest(BaseModel):
        name: str = Field(..., min_length=1)
        schedule: PolicySchedule
        retention_count: int = Field(default=7, ge=1)
        enabled: bool = True

    @app.post("/snapshots")
    def create_snapshot():
        stack = get_protection_stack()
        snapshot = stack.snapshot_manager.create_snapshot()
        return snapshot.model_dump()

    @app.get("/snapshots")
    def list_snapshots():
        stack = get_protection_stack()
        return [s.model_dump() for s in stack.snapshot_manager.list_snapshots()]

    @app.get("/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str):
        stack = get_protection_stack()
        snapshot = stack.snapshot_manager.get_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")
        return snapshot.model_dump()

    @app.delete("/snapshots/{snapshot_id}")
    def delete_snapshot(snapshot_id: str):
        stack = get_protection_stack()
        if not stack.snapshot_manager.delete_snapshot(snapshot_id):
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")
        return {"deleted": True, "snapshot_id": snapshot_id}

    @app.post("/snapshots/{snapshot_id}/restore")
    def restore_snapshot(snapshot_id: str):
        stack = get_protection_stack()
        job = stack.restore_service.restore_snapshot(snapshot_id)
        if job.status.value == "FAILED" and job.error:
            raise HTTPException(status_code=400, detail=job.error)
        return job.model_dump()

    @app.post("/backups")
    def create_backup(body: BackupCreateRequest = BackupCreateRequest()):
        stack = get_protection_stack()
        backup = stack.backup_service.create_backup(
            backup_type=body.backup_type,
            base_backup_id=body.base_backup_id,
        )
        return backup.model_dump()

    @app.get("/backups")
    def list_backups():
        stack = get_protection_stack()
        return [b.model_dump() for b in stack.backup_service.list_backups()]

    @app.get("/backups/{backup_id}")
    def get_backup(backup_id: str):
        stack = get_protection_stack()
        backup = stack.backup_service.get_backup(backup_id)
        if not backup:
            raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found")
        return backup.model_dump()

    @app.post("/backups/{backup_id}/restore")
    def restore_backup(backup_id: str):
        stack = get_protection_stack()
        job = stack.restore_service.restore_backup(backup_id, stack.backup_service)
        if job.status.value == "FAILED" and job.error:
            raise HTTPException(status_code=400, detail=job.error)
        return job.model_dump()

    @app.post("/snapshot-policies")
    def create_snapshot_policy(body: SnapshotPolicyRequest):
        stack = get_protection_stack()
        policy = stack.scheduler.create_policy(
            name=body.name,
            schedule=body.schedule,
            retention_count=body.retention_count,
            enabled=body.enabled,
        )
        return policy.model_dump()

    @app.get("/snapshot-policies")
    def list_snapshot_policies():
        stack = get_protection_stack()
        return [p.model_dump() for p in stack.scheduler.list_policies()]

    @app.get("/restore-jobs")
    def list_restore_jobs():
        stack = get_protection_stack()
        return [j.model_dump() for j in stack.restore_service.list_restore_jobs()]

    @app.get("/protection/metrics")
    def protection_metrics():
        stack = get_protection_stack()
        return stack.metrics.snapshot()

    @app.post("/protection/cleanup")
    def protection_cleanup(retention_count: int = 7):
        stack = get_protection_stack()
        return stack.retention_manager.run_cleanup(retention_count)

    return app


app = create_app()
