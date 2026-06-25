"""FastAPI node API — exposes storage engine over HTTP."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from metadata.models import WriteRequest
from node.consistency import ConsistencyLevel
from node.errors import QuorumNotSatisfiedError, ValidationError, VersionConflictError
from node.heartbeat_sender import HeartbeatSender
from node.hint_store import HintStore
from node.hint_worker import HintWorker
from node.hinted_handoff import HintedHandoff
from node.merkle import MerkleTree
from node.metadata_client import MetadataClient
from node.read_coordinator import ReadCoordinator
from node.read_repair import ReadRepair
from node.replica_client import ReplicaClient
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import ReplicateDeleteRequest, ReplicateRequest
from node.replication_service import ReplicationService
from node.replication_worker import ReplicationWorker
from node.storage_engine import StorageEngine

log = logging.getLogger(__name__)


class ConsistencyRequest(BaseModel):
    level: ConsistencyLevel


class ReadQuorumRequest(BaseModel):
    block_id: str = Field(..., min_length=1)
    consistency: Optional[ConsistencyLevel] = None
    repair: bool = True


class RepairRequest(BaseModel):
    block_id: str = Field(..., min_length=1)


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
    hint_store = HintStore(data_dir / "hints.db")

    metadata_client = (
        config.get("metadata_client")
        or MetadataClient(config["metadata_url"])
    )
    replica_client = config.get("replica_client") or ReplicaClient()

    consistency = config.get("consistency", ConsistencyLevel.QUORUM)

    def resolve_url(node_id, addresses):
        return metadata_client.resolve_node_url(node_id, addresses)

    hinted_handoff = HintedHandoff(
        node_id=config["node_id"],
        hint_store=hint_store,
        replica_client=replica_client,
        metrics=engine.metrics,
        resolve_url_fn=resolve_url,
    )

    replication_service = ReplicationService(
        node_id=config["node_id"],
        metadata_client=metadata_client,
        replica_client=replica_client,
        replica_manager=replica_manager,
        job_store=job_store,
        metrics=engine.metrics,
        hinted_handoff=hinted_handoff,
        consistency=consistency,
    )
    engine.set_replication_service(replication_service)

    read_repair = ReadRepair(
        node_id=config["node_id"],
        replica_client=replica_client,
        metrics=engine.metrics,
        resolve_url_fn=resolve_url,
    )

    read_coordinator = ReadCoordinator(
        node_id=config["node_id"],
        engine=engine,
        metadata_client=metadata_client,
        replica_client=replica_client,
        read_repair=read_repair,
        metrics=engine.metrics,
        consistency=consistency,
    )

    app.state.engine = engine
    app.state.replica_manager = replica_manager
    app.state.job_store = job_store
    app.state.hint_store = hint_store
    app.state.hinted_handoff = hinted_handoff
    app.state.replication_service = replication_service
    app.state.read_coordinator = read_coordinator
    app.state.read_repair = read_repair
    app.state.replication_worker = None
    app.state.hint_worker = None
    app.state.heartbeat = None

    if config.get("start_worker", True):
        worker = ReplicationWorker(replication_service)
        worker.start()
        app.state.replication_worker = worker

    if config.get("start_hint_worker", True):
        hint_worker = HintWorker(
            hinted_handoff=hinted_handoff,
            addresses_provider=lambda: metadata_client.get_node_addresses(),
        )
        hint_worker.start()
        app.state.hint_worker = hint_worker

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
    if app.state.hint_worker:
        app.state.hint_worker.stop()
    if app.state.heartbeat:
        app.state.heartbeat.stop()
    if app.state.read_repair:
        app.state.read_repair.shutdown()
    if app.state.engine:
        app.state.engine.close()
    if app.state.job_store:
        app.state.job_store.close()
    if app.state.hint_store:
        app.state.hint_store.close()

    app.state.replication_worker = None
    app.state.hint_worker = None
    app.state.replication_service = None
    app.state.read_coordinator = None
    app.state.read_repair = None
    app.state.replica_manager = None
    app.state.job_store = None
    app.state.hint_store = None
    app.state.hinted_handoff = None
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
    start_hint_worker: bool = True,
    consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
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
        "start_hint_worker": start_hint_worker,
        "consistency": consistency,
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
            snapshot = request.app.state.replication_service.get_last_quorum_snapshot()
            return {"ok": True, "block_id": body.block_id, "quorum": snapshot}
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except QuorumNotSatisfiedError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": str(exc),
                    "acks": exc.acks,
                    "required": exc.required,
                    "failed_nodes": exc.failed_nodes,
                },
            ) from exc

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
        row = request.app.state.engine.db.get_row(block_id)
        return {
            "block_id": record.block_id,
            "data": record.data,
            "version": record.version,
            "origin_lsn": record.origin_lsn,
            "updated_at_ms": row.get("updated_at_ms") if row else None,
            "deleted": record.deleted,
        }

    @app.delete("/delete/{block_id}")
    def delete_block(block_id: str, request: Request):
        try:
            request.app.state.engine.delete(block_id)
            return {"ok": True, "block_id": block_id}
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except QuorumNotSatisfiedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/quorum/status")
    def quorum_status(request: Request, block_id: Optional[str] = None):
        svc = request.app.state.replication_service
        snapshot = svc.get_last_quorum_snapshot()
        if block_id:
            return request.app.state.read_coordinator.get_quorum_status(block_id)
        return {
            "last_write_quorum": snapshot,
            "consistency": svc.consistency.value,
        }

    @app.get("/consistency")
    def get_consistency(request: Request):
        svc = request.app.state.replication_service
        return {"level": svc.consistency.value}

    @app.post("/consistency")
    def set_consistency(body: ConsistencyRequest, request: Request):
        request.app.state.replication_service.set_consistency(body.level)
        request.app.state.read_coordinator.set_consistency(body.level)
        return {"level": body.level.value}

    @app.post("/read-quorum")
    def read_quorum(body: ReadQuorumRequest, request: Request):
        result = request.app.state.read_coordinator.read(
            body.block_id,
            consistency=body.consistency,
            repair=body.repair,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Block '{body.block_id}' not found",
            )
        if not result.quorum_satisfied:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "read quorum not satisfied",
                    "copies_read": result.copies_read,
                    "outcome": result.outcome,
                },
            )
        return {
            "block_id": result.block_id,
            "data": result.data,
            "version": result.version,
            "node_id": result.node_id,
            "quorum_satisfied": result.quorum_satisfied,
            "copies_read": result.copies_read,
        }

    @app.post("/repair")
    def repair_block(body: RepairRequest, request: Request):
        coordinator = request.app.state.read_coordinator
        result = coordinator.read(body.block_id, repair=False)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Block '{body.block_id}' not found")

        locations = coordinator._metadata.get_block_locations(body.block_id)
        if not locations:
            return {"repaired": 0, "block_id": body.block_id}

        copies = coordinator._read_from_replicas(body.block_id, locations)
        from node.version_reconciliation import find_stale_replicas, select_latest

        successful = [c for c in copies if not c.deleted]
        latest = select_latest(successful)
        if latest is None:
            raise HTTPException(status_code=404, detail="no valid copies found")

        stale = find_stale_replicas(successful, latest)
        addresses = coordinator._metadata.get_node_addresses()
        repaired = request.app.state.read_repair.repair_sync(latest, stale, addresses)
        return {"repaired": repaired, "block_id": body.block_id, "stale_nodes": [s.node_id for s in stale]}

    @app.get("/hints")
    def list_hints(request: Request):
        hints = request.app.state.hinted_handoff.list_hints()
        return [h.model_dump() for h in hints]

    @app.get("/hints/pending")
    def list_pending_hints(request: Request):
        hints = request.app.state.hinted_handoff.list_pending()
        return [h.model_dump() for h in hints]

    @app.post("/hints/replay")
    def replay_hints(request: Request):
        addresses = request.app.state.replication_service._metadata.get_node_addresses()
        delivered = request.app.state.hinted_handoff.replay_pending(addresses)
        return {"delivered": delivered}

    @app.get("/replication/consistency")
    def replication_consistency(request: Request, block_id: Optional[str] = None):
        svc = request.app.state.replication_service
        if block_id:
            return svc.get_consistency_info(block_id)
        return {
            "consistency_level": svc.consistency.value,
            "last_quorum": svc.get_last_quorum_snapshot(),
        }

    @app.get("/merkle")
    def merkle_root(request: Request):
        engine = request.app.state.engine
        blocks = {}
        for block_id in engine.list_blocks():
            record = engine.read_block(block_id)
            if record and not record.deleted:
                blocks[block_id] = (record.data, record.version)
        tree = MerkleTree(blocks)
        return {
            "root_hash": tree.root_hash,
            "block_count": tree.block_count,
        }

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
            "write_quorum_failures": stats.get("write_quorum_failures", 0),
            "read_quorum_failures": stats.get("read_quorum_failures", 0),
            "read_repairs": stats.get("read_repairs", 0),
            "hint_deliveries": stats.get("hint_deliveries", 0),
            "hint_failures": stats.get("hint_failures", 0),
            "quorum_latency_ms": stats.get("quorum_latency_ms", 0.0),
        }

    @app.get("/stats")
    def stats(request: Request):
        return request.app.state.engine.get_stats()

    return app
