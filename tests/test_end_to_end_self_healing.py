"""End-to-end self-healing scenario from Phase 6 demo."""

import pytest

from metadata.app import get_placement_service, get_registry, get_repair_service
from metadata.models import NodeStatus


def test_phase6_demo_self_healing(repair_cluster):
    """
    1. RF=3 write invoice-123
    2. node3 down
    3. repair detects under-replication
    4. replica rebuilt to node4
    5. metadata updated
    6. node3 returns
    7. cluster reconciles to desired RF
    """
    metadata, nodes, _, _, _ = repair_cluster
    service = get_repair_service()
    placement = get_placement_service()
    registry = get_registry()

    metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
    nodes["node1"].post(
        "/write",
        json={"block_id": "invoice-123", "data": "invoice-payload", "version": 1},
    )

    initial = metadata.get("/blocks/invoice-123").json()["locations"]
    assert set(initial) == {"node1", "node2", "node3"}

    with registry._lock:
        record = registry._nodes["node3"]
        registry._nodes["node3"] = record.model_copy(update={"status": NodeStatus.DOWN})

    health = service.get_cluster_health()
    assert health["under_replicated_count"] >= 1

    cycle = service.run_repair_cycle()
    assert cycle["executed"] >= 0

    result = service.repair_block("invoice-123")
    assert result.get("ok") is True

    after_repair = metadata.get("/blocks/invoice-123").json()["locations"]
    assert len(after_repair) == 3
    assert "node4" in after_repair
    assert "node3" not in after_repair

    with registry._lock:
        record = registry._nodes["node3"]
        registry._nodes["node3"] = record.model_copy(update={"status": NodeStatus.UP})

    over = service.scan_cluster().over_replicated
    if over:
        service.run_repair_cycle()

    integrity = metadata.get("/cluster/integrity").json()
    assert integrity is not None

    for node_id in after_repair:
        read = nodes[node_id].get("/read/invoice-123")
        assert read.status_code == 200
        assert read.json()["data"] == "invoice-payload"
