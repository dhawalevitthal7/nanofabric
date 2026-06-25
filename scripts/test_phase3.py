#!/usr/bin/env python3
"""Phase 3 integration smoke test — exercises placement APIs end-to-end."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from metadata.app import create_app
from metadata.metadata_store import MetadataStore


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


def main() -> None:
    print("=" * 60)
    print("NanoFabric Phase 3 — Integration Smoke Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "metadata.db"

        # --- Session 1: fresh metadata service ---
        print("\n[1] Starting metadata service (session 1)...")
        with TestClient(create_app(db_path=db_path)) as client:
            for i in range(1, 4):
                r = client.post(
                    "/register",
                    json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
                )
                check(r.status_code == 200, f"Register node{i}")

            summary = client.get("/cluster-summary").json()
            check(
                summary == {"node1": "UP", "node2": "UP", "node3": "UP"},
                "All 3 nodes UP in cluster summary",
            )

            # --- Round-robin RF=1 ---
            print("\n[2] Testing round-robin placement (RF=1)...")
            placements_rf1 = []
            for n in range(1, 5):
                bid = f"block-rf1-{n}"
                r = client.post("/allocate", json={"block_id": bid, "rf": 1})
                check(r.status_code == 200, f"Allocate {bid}")
                placements_rf1.append(r.json()["nodes"][0])

            check(
                placements_rf1 == ["node1", "node2", "node3", "node1"],
                f"Round-robin RF=1: {placements_rf1}",
            )

            # --- RF=2 allocation ---
            print("\n[3] Testing RF=2 allocation...")
            r = client.post(
                "/allocate",
                json={"block_id": "invoice-123", "rf": 2},
            )
            check(r.status_code == 200, "Allocate invoice-123 with RF=2")
            nodes = r.json()["nodes"]
            check(nodes == ["node2", "node3"], f"invoice-123 placed on {nodes}")

            # --- Block lookup ---
            print("\n[4] Testing block lookup...")
            r = client.get("/blocks/invoice-123")
            check(r.status_code == 200, "GET /blocks/invoice-123")
            check(
                r.json()["locations"] == ["node2", "node3"],
                f"Locations: {r.json()['locations']}",
            )

            # --- Node inventory ---
            print("\n[5] Testing node inventory...")
            r = client.get("/nodes/node2/blocks")
            check(r.status_code == 200, "GET /nodes/node2/blocks")
            blocks_on_node2 = r.json()["blocks"]
            check("invoice-123" in blocks_on_node2, "invoice-123 in node2 inventory")

            # --- Full placements map ---
            print("\n[6] Testing /placements...")
            r = client.get("/placements")
            check(r.status_code == 200, "GET /placements")
            all_placements = r.json()
            check("invoice-123" in all_placements, "invoice-123 in placements map")
            check(len(all_placements) == 5, f"Total blocks placed: {len(all_placements)}")

            # --- Metadata stats ---
            print("\n[7] Testing /metadata/stats...")
            r = client.get("/metadata/stats")
            check(r.status_code == 200, "GET /metadata/stats")
            stats = r.json()
            check(stats["total_blocks"] == 5, f"total_blocks={stats['total_blocks']}")
            check(stats["total_placements"] == 6, f"total_placements={stats['total_placements']}")

            # --- Heartbeat with node stats ---
            print("\n[8] Testing heartbeat with node statistics...")
            r = client.post(
                "/heartbeat",
                json={
                    "node_id": "node1",
                    "timestamp": 1_700_000_000_000,
                    "block_count": 120,
                    "used_bytes": 10_485_760,
                    "last_lsn": 4200,
                },
            )
            check(r.status_code == 200, "Heartbeat with stats")

            store = MetadataStore(db_path)
            row = store._conn.execute(
                "SELECT block_count, used_bytes, last_lsn FROM nodes WHERE node_id = ?",
                ("node1",),
            ).fetchone()
            store.close()
            check(row["block_count"] == 120, "Node stats block_count persisted")
            check(row["used_bytes"] == 10_485_760, "Node stats used_bytes persisted")
            check(row["last_lsn"] == 4200, "Node stats last_lsn persisted")

            # --- Duplicate allocation ---
            print("\n[9] Testing duplicate allocation (expect 409)...")
            r = client.post(
                "/allocate",
                json={"block_id": "invoice-123", "rf": 2},
            )
            check(r.status_code == 409, "Duplicate allocate returns 409")

            # --- Missing block ---
            print("\n[10] Testing missing block lookup (expect 404)...")
            r = client.get("/blocks/does-not-exist")
            check(r.status_code == 404, "Missing block returns 404")

        # --- Session 2: simulate metadata restart ---
        print("\n[11] Simulating metadata restart (session 2)...")
        with TestClient(create_app(db_path=db_path)) as client2:
            for i in range(1, 4):
                client2.post(
                    "/register",
                    json={"node_id": f"node{i}", "address": f"node{i}:800{i}"},
                )

            r = client2.get("/blocks/invoice-123")
            check(r.status_code == 200, "Block lookup after restart")
            check(
                r.json()["locations"] == ["node2", "node3"],
                f"Placements survived restart: {r.json()['locations']}",
            )

            r = client2.get("/metadata/stats")
            check(r.status_code == 200, "Stats after restart")
            check(
                r.json()["total_blocks"] == 5,
                f"Block count after restart: {r.json()['total_blocks']}",
            )

            r = client2.get("/placements")
            check("invoice-123" in r.json(), "Placements map intact after restart")

            # Round-robin should continue from where it left off
            r = client2.post(
                "/allocate",
                json={"block_id": "block-after-restart", "rf": 1},
            )
            check(r.status_code == 200, "Allocate after restart")
            check(
                r.json()["nodes"] == ["node3"],
                f"Round-robin resumed correctly after restart: {r.json()['nodes']}",
            )

    print("\n" + "=" * 60)
    print("ALL PHASE 3 INTEGRATION CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
