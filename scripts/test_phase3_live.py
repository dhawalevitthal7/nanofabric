#!/usr/bin/env python3
"""Live HTTP smoke test — run against a running metadata service."""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"


def main() -> None:
    print(f"Live metadata test against {BASE}\n")

    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        for i in range(1, 4):
            r = client.post("/register", json={"node_id": f"node{i}", "address": f"node{i}:800{i}"})
            assert r.status_code == 200, f"register node{i} failed: {r.status_code}"
        print("  PASS  register 3 nodes")

        for i in range(1, 4):
            r = client.post("/heartbeat", json={"node_id": f"node{i}"})
            assert r.status_code == 200, f"heartbeat node{i} failed: {r.status_code}"
        print("  PASS  heartbeat all nodes")

        summary = client.get("/cluster-summary").json()
        assert all(v == "UP" for v in summary.values()), f"expected all UP: {summary}"
        print(f"  PASS  cluster-summary: {summary}")

        block_id = "live-invoice-123"
        r = client.post("/allocate", json={"block_id": block_id, "rf": 2})
        if r.status_code == 409:
            client.get(f"/blocks/{block_id}")  # from prior run — still valid
            print(f"  PASS  allocate skipped (409 — block already exists from prior run)")
        else:
            assert r.status_code == 200, f"allocate failed: {r.status_code} {r.text}"
            print(f"  PASS  allocate {block_id} -> {r.json()['nodes']}")

        loc = client.get(f"/blocks/{block_id}").json()
        assert len(loc["locations"]) == 2
        print(f"  PASS  lookup locations: {loc['locations']}")

        node_id = loc["locations"][0]
        inv = client.get(f"/nodes/{node_id}/blocks").json()
        assert block_id in inv["blocks"]
        print(f"  PASS  node inventory on {node_id}")

        stats = client.get("/metadata/stats").json()
        assert stats["total_blocks"] >= 1
        print(f"  PASS  metadata stats: {stats}")

        r = client.post(
            "/heartbeat",
            json={
                "node_id": "node1",
                "block_count": 50,
                "used_bytes": 2048,
                "last_lsn": 100,
            },
        )
        assert r.status_code == 200
        print("  PASS  heartbeat with node stats")

        r = client.post("/allocate", json={"block_id": block_id, "rf": 2})
        assert r.status_code == 409
        print("  PASS  duplicate allocate returns 409")

    print("\nALL LIVE HTTP CHECKS PASSED")


if __name__ == "__main__":
    main()
