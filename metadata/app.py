"""FastAPI metadata service — cluster brain for membership, health, and placement."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException

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

log = logging.getLogger(__name__)

_registry: Optional[MembershipRegistry] = None
_detector: Optional[FailureDetector] = None
_store: Optional[MetadataStore] = None
_placement_registry: Optional[PlacementRegistry] = None
_inventory: Optional[NodeInventory] = None
_placement_service: Optional[PlacementService] = None


def get_registry() -> MembershipRegistry:
    if _registry is None:
        raise RuntimeError("Membership registry is not initialized")
    return _registry


def get_placement_service() -> PlacementService:
    if _placement_service is None:
        raise RuntimeError("Placement service is not initialized")
    return _placement_service


def get_store() -> MetadataStore:
    if _store is None:
        raise RuntimeError("Metadata store is not initialized")
    return _store


def _default_db_path() -> Path:
    return Path(os.environ.get("METADATA_DB_PATH", "metadata.db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _detector, _store, _placement_registry, _inventory, _placement_service

    db_path = app.state.db_path if hasattr(app.state, "db_path") else _default_db_path()
    _store = MetadataStore(db_path)
    _registry = MembershipRegistry()
    _placement_registry = PlacementRegistry()
    _inventory = NodeInventory()
    policy = RoundRobinPlacementPolicy()
    _placement_service = PlacementService(
        registry=_registry,
        placement_registry=_placement_registry,
        inventory=_inventory,
        store=_store,
        policy=policy,
    )
    _placement_service.recover()
    _detector = FailureDetector(_registry)
    _detector.start()
    log.info("metadata service started", extra={"db_path": str(db_path)})
    yield
    if _detector:
        _detector.stop()
    if _store:
        _store.close()
    _detector = None
    _placement_service = None
    _inventory = None
    _placement_registry = None
    _store = None
    _registry = None
    log.info("metadata service stopped")


def create_app(db_path: Optional[str | Path] = None) -> FastAPI:
    app = FastAPI(title="NanoFabric Metadata Service", lifespan=lifespan)
    if db_path is not None:
        app.state.db_path = Path(db_path)

    @app.get("/health")
    def health():
        registry = get_registry()
        summary = registry.get_cluster_summary()
        up_count = sum(1 for status in summary.values() if status == "UP")
        return {
            "status": "ok",
            "nodes_total": len(summary),
            "nodes_up": up_count,
            "nodes_down": len(summary) - up_count,
        }

    @app.post("/register", response_model=NodeRecord)
    def register(request: RegisterRequest):
        record = get_registry().register(request.node_id, request.address)
        get_store().upsert_node(request.node_id, status="UP", last_seen=record.last_seen)
        return record

    @app.post("/heartbeat", response_model=NodeRecord)
    def heartbeat(request: HeartbeatRequest):
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
        try:
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

    return app


app = create_app()
