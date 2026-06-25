"""Phase 6 self-healing demo — node failure, re-replication, and recovery."""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
for p in (ROOT, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient

from metadata.app import create_app as create_metadata_app, get_repair_service
from metadata.models import NodeStatus
from node.api_server import create_app as create_node_app
from replication_helpers import (
    RoutingNodeClient,
    RoutingReplicaClient,
    TestMetadataClient,
)


def _shutdown(node_clients, metadata):
    """Close app lifecycles before temp-dir cleanup (required on Windows)."""
    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata.__exit__(None, None, None)


def main():
    tmp_path = Path(tempfile.mkdtemp())
    node_clients = {}
    metadata = None
    repair = None

    try:
        db_path = tmp_path / "metadata.db"

        from metadata import app as metadata_app_module
        from metadata.placement_policy import RoundRobinPlacementPolicy
        from cluster.repair_factory import build_repair_stack
        from cluster.repair_metrics import RepairMetrics

        app = create_metadata_app(db_path=db_path)
        app.state.start_repair_worker = False
        metadata = TestClient(app)
        metadata.__enter__()

        for i in range(1, 5):
            metadata.post(
                "/register",
                json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
            )

        meta_client = TestMetadataClient(metadata)
        routing = RoutingReplicaClient(node_clients)
        routing_node = RoutingNodeClient(node_clients)

        for i in range(1, 5):
            node_id = f"node{i}"
            node_app = create_node_app(
                node_id=node_id,
                data_dir=str(tmp_path / node_id),
                metadata_url="http://test-metadata",
                address=f"{node_id}:800{i}",
                metadata_client=meta_client,
                replica_client=routing,
                start_worker=False,
                start_heartbeat=False,
                start_hint_worker=False,
                run_node_recovery=False,
            )
            tc = TestClient(node_app)
            tc.__enter__()
            node_clients[node_id] = tc

        placement = metadata_app_module.get_placement_service()
        registry = metadata_app_module.get_registry()
        policy = RoundRobinPlacementPolicy()

        # Replace metadata's repair stack with one wired to in-process nodes.
        try:
            get_repair_service()._job_store.close()
        except RuntimeError:
            pass

        metadata_app_module._repair_metrics = RepairMetrics()
        repair = build_repair_stack(
            placement_service=placement,
            membership=registry,
            placement_policy=policy,
            db_path=db_path.parent / "repair.db",
            replica_client=routing,
            node_client=routing_node,
            metrics=metadata_app_module._repair_metrics,
        )
        metadata_app_module._repair_service = repair

        print("1. Allocate invoice-123 with RF=3")
        metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})

        print("2. Write invoice-123 from node1")
        node_clients["node1"].post(
            "/write",
            json={"block_id": "invoice-123", "data": "invoice-payload", "version": 1},
        )
        print("   locations:", metadata.get("/blocks/invoice-123").json()["locations"])

        print("3. Mark node3 DOWN")
        with registry._lock:
            record = registry._nodes["node3"]
            registry._nodes["node3"] = record.model_copy(update={"status": NodeStatus.DOWN})

        health = repair.get_cluster_health()
        print(f"   under-replicated: {health['under_replicated_count']}")

        print("4. Run repair — rebuild replica on node4")
        result = repair.repair_block("invoice-123")
        print(f"   repair result: ok={result.get('ok')}")

        after = metadata.get("/blocks/invoice-123").json()["locations"]
        print(f"   updated locations: {after}")

        print("5. Start node3 — cluster reconciles")
        with registry._lock:
            record = registry._nodes["node3"]
            registry._nodes["node3"] = record.model_copy(update={"status": NodeStatus.UP})
        repair.run_repair_cycle()

        integrity = repair.get_cluster_integrity()
        print(f"6. Integrity check: healthy={integrity['healthy']}")

        for node_id in after:
            data = node_clients[node_id].get("/read/invoice-123").json()["data"]
            assert data == "invoice-payload"

        print("\nPhase 6 demo PASSED")
    finally:
        if metadata is not None:
            _shutdown(node_clients, metadata)
        shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    main()
