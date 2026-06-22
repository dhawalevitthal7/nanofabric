"""FastAPI metadata service — cluster brain for membership and health."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException

from metadata.failure_detector import FailureDetector
from metadata.membership import MembershipRegistry
from metadata.models import HeartbeatRequest, NodeRecord, RegisterRequest

log = logging.getLogger(__name__)

_registry: Optional[MembershipRegistry] = None
_detector: Optional[FailureDetector] = None


def get_registry() -> MembershipRegistry:
    if _registry is None:
        raise RuntimeError("Membership registry is not initialized")
    return _registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _detector
    _registry = MembershipRegistry()
    _detector = FailureDetector(_registry)
    _detector.start()
    log.info("metadata service started")
    yield
    if _detector:
        _detector.stop()
    _detector = None
    _registry = None
    log.info("metadata service stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="NanoFabric Metadata Service", lifespan=lifespan)

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
        return get_registry().register(request.node_id, request.address)

    @app.post("/heartbeat", response_model=NodeRecord)
    def heartbeat(request: HeartbeatRequest):
        try:
            return get_registry().heartbeat(request.node_id, request.timestamp)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/nodes")
    def list_nodes():
        nodes = get_registry().get_all_nodes()
        return {node_id: record.model_dump() for node_id, record in nodes.items()}

    @app.get("/cluster-summary")
    def cluster_summary():
        return get_registry().get_cluster_summary()

    return app


app = create_app()
