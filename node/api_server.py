"""FastAPI node API — exposes storage engine over HTTP."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from metadata.models import WriteRequest
from node.errors import ValidationError, VersionConflictError
from node.heartbeat_sender import HeartbeatSender
from node.metadata_client import MetadataClient
from node.replica_client import ReplicaClient
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import ReplicateDeleteRequest, ReplicateRequest
from node.replication_service import ReplicationService
from node.replication_worker import ReplicationWorker
from node.storage_engine import StorageEngine

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = app.state.config
    data_dir = Path(config["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)

    engine = StorageEngine(
        data_dir=data_dir,
        node_id=config["node_id"],
    )
    replica_manager = ReplicaManager()
    job_store = ReplicationJobStore(data_dir / "replication.db")

    metadata_client = (
        config.get("metadata_client")
        or MetadataClient(config["metadata_url"])
    )
    replica_client = config.get("replica_client") or ReplicaClient()

    replication_service = ReplicationService(
        node_id=config["node_id"],
        metadata_client=metadata_client,
        replica_client=replica_client,
        replica_manager=replica_manager,
        job_store=job_store,
        metrics=engine.metrics,
    )
    engine.set_replication_service(replication_service)

    app.state.engine = engine
    app.state.replica_manager = replica_manager
    app.state.job_store = job_store
    app.state.replication_service = replication_service
    app.state.replication_worker = None
    app.state.heartbeat = None

    if config.get("start_worker", True):
        worker = ReplicationWorker(replication_service)
        worker.start()
        app.state.replication_worker = worker

    if config.get("start_heartbeat", True):
        heartbeat = HeartbeatSender(
            metadata_url=config["metadata_url"],
            node_id=config["node_id"],
            address=config["address"],
            stats_provider=lambda: app.state.engine.get_stats(),
        )
        heartbeat.start()
        app.state.heartbeat = heartbeat

    log.info("node API started", extra={"node_id": config["node_id"]})
    yield

    if app.state.replication_worker:
        app.state.replication_worker.stop()
    if app.state.heartbeat:
        app.state.heartbeat.stop()
    if app.state.engine:
        app.state.engine.close()
    if app.state.job_store:
        app.state.job_store.close()

    app.state.replication_worker = None
    app.state.replication_service = None
    app.state.replica_manager = None
    app.state.job_store = None
    app.state.heartbeat = None
    app.state.engine = None
    log.info("node API stopped")


def create_app(
    node_id: str,
    data_dir: str,
    metadata_url: str,
    address: str,
    replica_client: Optional[ReplicaClient] = None,
    metadata_client: Optional[MetadataClient] = None,
    start_worker: bool = True,
    start_heartbeat: bool = True,
) -> FastAPI:
    app = FastAPI(title=f"NanoFabric Node ({node_id})", lifespan=lifespan)
    app.state.config = {
        "node_id": node_id,
        "data_dir": data_dir,
        "metadata_url": metadata_url,
        "address": address,
        "replica_client": replica_client,
        "metadata_client": metadata_client,
        "start_worker": start_worker,
        "start_heartbeat": start_heartbeat,
    }

    @app.get("/health")
    def health(request: Request):
        stats = request.app.state.engine.get_stats()
        return {
            "status": "ok",
            "node_id": stats["node_id"],
            "block_count": stats["block_count"],
        }

    @app.post("/write")
    def write_block(body: WriteRequest, request: Request):
        try:
            request.app.state.engine.write(body.block_id, body.data, body.version)
            return {"ok": True, "block_id": body.block_id}
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/replicate")
    def replicate_write(body: ReplicateRequest, request: Request):
        engine = request.app.state.engine
        try:
            version, _ = engine.write_local(
                body.block_id,
                body.data,
                body.version,
                origin_node_id=body.origin_node_id,
                origin_lsn=body.lsn,
                allow_idempotent=True,
            )
            return {
                "status": "success",
                "node_id": engine.node_id,
                "version": version,
            }
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/replicate-delete")
    def replicate_delete(body: ReplicateDeleteRequest, request: Request):
        engine = request.app.state.engine
        try:
            version, _ = engine.delete_local(
                body.block_id,
                version=body.version,
                origin_node_id=body.origin_node_id,
                origin_lsn=body.lsn,
                allow_idempotent=True,
            )
            return {
                "status": "success",
                "node_id": engine.node_id,
                "version": version,
            }
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/read/{block_id}")
    def read_block(block_id: str, request: Request):
        record = request.app.state.engine.read_block(block_id)
        if record is None or record.deleted:
            raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
        return {
            "block_id": record.block_id,
            "data": record.data,
            "version": record.version,
        }

    @app.delete("/delete/{block_id}")
    def delete_block(block_id: str, request: Request):
        try:
            request.app.state.engine.delete(block_id)
            return {"ok": True, "block_id": block_id}
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/replication/jobs")
    def list_replication_jobs(request: Request):
        jobs = request.app.state.job_store.list_all_jobs()
        return [job.model_dump() for job in jobs]

    @app.get("/replication/failed")
    def list_failed_replications(request: Request):
        states = request.app.state.replica_manager.list_failed_replications()
        return [state.model_dump() for state in states]

    @app.get("/replication/state/{block_id}")
    def get_replication_state(block_id: str, request: Request):
        state = request.app.state.replica_manager.get_replica_state(block_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail=f"No replication state for block '{block_id}'",
            )
        return state.model_dump()

    @app.get("/replication/stats")
    def replication_stats(request: Request):
        stats = request.app.state.engine.get_stats()
        return {
            "successful_replications": stats.get("successful_replications", 0),
            "failed_replications": stats.get("failed_replications", 0),
            "retry_count": stats.get("retry_count", 0),
            "replication_latency_ms": stats.get("replication_latency_ms", 0.0),
            "degraded_replications": stats.get("degraded_replications", 0),
        }

    @app.get("/stats")
    def stats(request: Request):
        return request.app.state.engine.get_stats()

    return app
