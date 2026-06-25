#!/usr/bin/env python3
"""Phase 4 integration smoke test — single write, automatic replication."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
for p in (ROOT, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient

from metadata.app import create_app as create_metadata_app
from node.api_server import create_app as create_node_app
from replication_helpers import RoutingReplicaClient, TestMetadataClient


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


def check(cond: bool, msg: str) -> None:
    if cond:
        ok(msg)
    else:
        fail(msg)


def build_cluster(tmp_path: Path):
    db_path = tmp_path / "metadata.db"
    metadata = TestClient(create_metadata_app(db_path=db_path))
    metadata.__enter__()

    for i in range(1, 4):
        r = metadata.post(
            "/register",
            json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
        )
        check(r.status_code == 200, f"Register node{i}")

    node_clients = {}
    metadata_client = TestMetadataClient(metadata)
    routing = RoutingReplicaClient(node_clients)

    for i in range(1, 4):
        node_id = f"node{i}"
        app = create_node_app(
            node_id=node_id,
            data_dir=str(tmp_path / node_id),
            metadata_url="http://test-metadata",
            address=f"{node_id}:800{i}",
            metadata_client=metadata_client,
            replica_client=routing,
            start_worker=False,
            start_heartbeat=False,
        )
        tc = TestClient(app)
        tc.__enter__()
        node_clients[node_id] = tc

    return metadata, node_clients


def teardown_cluster(metadata, node_clients) -> None:
    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata.__exit__(None, None, None)


def main() -> None:
    print("=" * 60)
    print("NanoFabric Phase 4 — Integration Smoke Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        metadata, nodes = build_cluster(tmp_path)

        try:
            print("\n[1] Allocate block with RF=3...")
            r = metadata.post("/allocate", json={"block_id": "invoice-123", "rf": 3})
            check(r.status_code == 200, "Allocate invoice-123 RF=3")
            locations = r.json()["nodes"]
            check(len(locations) == 3, f"Placed on 3 nodes: {locations}")
            primary = locations[0]
            replicas = [n for n in locations if n != primary]

            print("\n[2] Single write to primary...")
            r = nodes[primary].post(
                "/write",
                json={"block_id": "invoice-123", "data": "hello"},
            )
            check(r.status_code == 200, f"Write to {primary}")
            check(r.json()["ok"] is True, "Write response ok")

            print("\n[3] Verify primary has data...")
            r = nodes[primary].get("/read/invoice-123")
            check(r.status_code == 200, f"Read from {primary}")
            check(r.json()["data"] == "hello", f"Primary data: {r.json()['data']!r}")

            print("\n[4] Verify replicas received data automatically...")
            for replica in replicas:
                r = nodes[replica].get("/read/invoice-123")
                check(r.status_code == 200, f"Read from replica {replica}")
                check(
                    r.json()["data"] == "hello",
                    f"Replica {replica} data: {r.json()['data']!r}",
                )

            print("\n[5] Replication state and stats...")
            r = nodes[primary].get("/replication/state/invoice-123")
            check(r.status_code == 200, "GET /replication/state/invoice-123")
            check(r.json()["state"] == "REPLICATED", f"State: {r.json()['state']}")

            stats = nodes[primary].get("/replication/stats").json()
            check(
                stats["successful_replications"] >= len(replicas),
                f"successful_replications={stats['successful_replications']}",
            )

            print("\n[6] Idempotent replicate (duplicate request)...")
            payload = {
                "block_id": "invoice-123",
                "data": "hello",
                "version": 1,
                "lsn": 10,
                "origin_node_id": primary,
            }
            r1 = nodes[replicas[0]].post("/replicate", json=payload)
            r2 = nodes[replicas[0]].post("/replicate", json=payload)
            check(r1.status_code == 200 and r2.status_code == 200, "Duplicate replicate OK")

            print("\n[7] Delete replication (tombstones)...")
            r = nodes[primary].delete("/delete/invoice-123")
            check(r.status_code == 200, "Delete on primary")
            for node_id in locations:
                r = nodes[node_id].get("/read/invoice-123")
                check(r.status_code == 404, f"Tombstone on {node_id} (404)")

            print("\n[8] RF=2 single-write replication...")
            r = metadata.post("/allocate", json={"block_id": "invoice-rf2", "rf": 2})
            check(r.status_code == 200, "Allocate invoice-rf2 RF=2")
            loc2 = r.json()["nodes"]
            p2 = loc2[0]
            nodes[p2].post("/write", json={"block_id": "invoice-rf2", "data": "rf2-data"})
            for n in loc2:
                r = nodes[n].get("/read/invoice-rf2")
                check(r.status_code == 200 and r.json()["data"] == "rf2-data", f"RF=2 read {n}")

        finally:
            teardown_cluster(metadata, nodes)

    print("\n" + "=" * 60)
    print("ALL PHASE 4 INTEGRATION CHECKS PASSED")
    print("Client performed ONE write — replicas converged automatically.")
    print("=" * 60)


if __name__ == "__main__":
    main()
