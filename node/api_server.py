"""FastAPI node API — exposes storage engine over HTTP."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException

from metadata.models import WriteRequest
from node.errors import ValidationError, VersionConflictError
from node.heartbeat_sender import HeartbeatSender
from node.storage_engine import StorageEngine

log = logging.getLogger(__name__)

_engine: Optional[StorageEngine] = None
_heartbeat: Optional[HeartbeatSender] = None


def get_engine() -> StorageEngine:
    if _engine is None:
        raise RuntimeError("Storage engine is not initialized")
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _heartbeat
    config = app.state.config
    _engine = StorageEngine(
        data_dir=config["data_dir"],
        node_id=config["node_id"],
    )
    _heartbeat = HeartbeatSender(
        metadata_url=config["metadata_url"],
        node_id=config["node_id"],
        address=config["address"],
        stats_provider=lambda: get_engine().get_stats(),
    )
    _heartbeat.start()
    log.info("node API started", extra={"node_id": config["node_id"]})
    yield
    if _heartbeat:
        _heartbeat.stop()
    if _engine:
        _engine.close()
    _heartbeat = None
    _engine = None
    log.info("node API stopped")


def create_app(
    node_id: str,
    data_dir: str,
    metadata_url: str,
    address: str,
) -> FastAPI:
    app = FastAPI(title=f"NanoFabric Node ({node_id})", lifespan=lifespan)
    app.state.config = {
        "node_id": node_id,
        "data_dir": data_dir,
        "metadata_url": metadata_url,
        "address": address,
    }

    @app.get("/health")
    def health():
        stats = get_engine().get_stats()
        return {
            "status": "ok",
            "node_id": stats["node_id"],
            "block_count": stats["block_count"],
        }

    @app.post("/write")
    def write_block(request: WriteRequest):
        try:
            get_engine().write(request.block_id, request.data, request.version)
            return {"ok": True, "block_id": request.block_id}
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/read/{block_id}")
    def read_block(block_id: str):
        record = get_engine().read_block(block_id)
        if record is None or record.deleted:
            raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
        return {
            "block_id": record.block_id,
            "data": record.data,
            "version": record.version,
        }

    @app.get("/stats")
    def stats():
        return get_engine().get_stats()

    return app
