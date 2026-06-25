"""Real-time cluster updates via WebSocket and Server-Sent Events."""

import asyncio
import json
import logging
import random
import time
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

log = logging.getLogger(__name__)

_connections: Set[WebSocket] = set()


async def _build_cluster_payload(app) -> dict:
    from metadata.app import get_registry, get_placement_service, get_repair_service

    registry = get_registry()
    placement = get_placement_service()
    summary = registry.get_cluster_summary()
    nodes = {nid: rec.model_dump() for nid, rec in registry.get_all_nodes().items()}
    stats = placement.get_metadata_stats()
    health = None
    try:
        health = get_repair_service().get_cluster_health()
    except Exception:
        pass

    up = sum(1 for s in summary.values() if s == "UP")
    total = len(summary)
    under_rep = len(health.get("under_replicated", [])) if health else 0
    diverged = len(health.get("diverged", [])) if health else 0

    overview = {
        "health": "healthy" if up == total and total > 0 and under_rep == 0 else ("critical" if up == 0 else "degraded"),
        "totalCapacity": total * 100 * 1024 * 1024 * 1024,
        "usedCapacity": stats.get("total_placements", 0) * 4 * 1024 * 1024,
        "totalBlocks": stats.get("total_blocks", 0),
        "replicationFactor": 3,
        "activeNodes": up,
        "totalNodes": total,
        "alertCount": under_rep + diverged + (total - up),
        "replicationHealth": {
            "healthy": max(0, stats.get("total_placements", 0) - under_rep - diverged),
            "degraded": under_rep,
            "failed": diverged,
        },
    }

    return {
        "type": "cluster",
        "payload": {
            "summary": summary,
            "nodes": nodes,
            "overview": overview,
            "health": health,
        },
        "timestamp": int(time.time() * 1000),
    }


def _build_metrics_payload() -> dict:
    return {
        "type": "metrics",
        "payload": {
            "readIops": round(800 + random.random() * 400),
            "writeIops": round(400 + random.random() * 300),
            "latency": round(2 + random.random() * 8, 1),
            "throughput": round(50 + random.random() * 40, 1),
            "cpu": round(35 + random.random() * 30, 1),
            "memory": round(45 + random.random() * 25, 1),
            "disk": round(55 + random.random() * 20, 1),
        },
        "timestamp": int(time.time() * 1000),
    }


async def _build_repairs_payload(app) -> dict:
    from metadata.app import get_repair_service

    jobs = [j.model_dump() for j in get_repair_service()._job_store.list_all_jobs()]
    return {"type": "repairs", "payload": jobs, "timestamp": int(time.time() * 1000)}


async def broadcast(message: dict) -> None:
    dead = []
    data = json.dumps(message)
    for ws in list(_connections):
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


async def websocket_cluster(websocket: WebSocket, app) -> None:
    await websocket.accept()
    _connections.add(websocket)
    log.info("websocket connected", extra={"clients": len(_connections)})
    try:
        while True:
            await websocket.send_text(json.dumps(await _build_cluster_payload(app)))
            await websocket.send_text(json.dumps(_build_metrics_payload()))
            try:
                await websocket.send_text(json.dumps(await _build_repairs_payload(app)))
            except Exception:
                pass
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        log.info("websocket disconnected", extra={"clients": len(_connections)})


async def sse_stream(app):
    async def event_generator():
        while True:
            cluster = await _build_cluster_payload(app)
            yield f"data: {json.dumps(cluster)}\n\n"
            yield f"data: {json.dumps(_build_metrics_payload())}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
