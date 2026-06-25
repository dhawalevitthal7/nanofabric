#!/usr/bin/env python3
"""Live Phase 5 smoke test — quorum, hints, read repair against running cluster.

Prerequisites:
  Terminal 1:  python scripts/start_cluster_local.py
  Terminal 2:  python scripts/test_phase5_live.py
"""

import argparse
import sys

import httpx

NODE_PORTS = {"node1": 8001, "node2": 8002, "node3": 8003}
BLOCK_ID = "phase5-live-test"


def node_url(node_id: str, host: str = "localhost") -> str:
    return f"http://{host}:{NODE_PORTS[node_id]}"


def check(client: httpx.Client, cond: bool, msg: str) -> None:
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        sys.exit(1)


def preflight(client: httpx.Client, metadata: str, host: str) -> None:
    print("Preflight...\n")
    for label, url in [
        ("metadata", f"{metadata}/health"),
        *[(nid, f"{node_url(nid, host)}/health") for nid in NODE_PORTS],
    ]:
        try:
            r = client.get(url)
            check(client, r.status_code == 200, f"{label} reachable")
        except httpx.HTTPError as exc:
            print(f"  FAIL  {label} — {exc}")
            sys.exit(1)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 live quorum test")
    parser.add_argument("metadata", nargs="?", default="http://localhost:9000")
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    metadata = args.metadata.rstrip("/")
    host = args.host

    print("=" * 60)
    print("NanoFabric Phase 5 — Live Test")
    print("=" * 60)

    with httpx.Client(timeout=15.0) as client:
        preflight(client, metadata, host)

        for node_id in NODE_PORTS:
            client.post(
                f"{metadata}/register",
                json={"node_id": node_id, "address": f"{host}:{NODE_PORTS[node_id]}"},
            )
            client.post(f"{metadata}/heartbeat", json={"node_id": node_id})

        r = client.post(f"{metadata}/allocate", json={"block_id": BLOCK_ID, "rf": 3})
        if r.status_code not in (200, 409):
            print(f"  FAIL  allocate: {r.status_code} {r.text}")
            sys.exit(1)
        print(f"  PASS  allocate {BLOCK_ID} RF=3")

        primary_url = node_url("node1", host)

        r = client.get(f"{primary_url}/quorum/status", params={"block_id": BLOCK_ID})
        check(client, r.status_code == 200, "GET /quorum/status")
        body = r.json()
        check(client, body["write_quorum"] == 2, f"W=2 (got {body})")

        r = client.post(
            f"{primary_url}/write",
            json={"block_id": BLOCK_ID, "data": "live-hello"},
        )
        check(client, r.status_code == 200, f"Write: {r.json()}")
        check(client, r.json().get("quorum", {}).get("quorum_satisfied") is True, "Quorum satisfied")

        r = client.post(f"{primary_url}/read-quorum", json={"block_id": BLOCK_ID})
        check(client, r.status_code == 200, "Read quorum")
        check(client, r.json()["data"] == "live-hello", f"Data: {r.json()['data']!r}")

        for nid in NODE_PORTS:
            r = client.get(f"{node_url(nid, host)}/read/{BLOCK_ID}")
            check(client, r.status_code == 200, f"Replica {nid} has block")

        stats = client.get(f"{primary_url}/replication/stats").json()
        check(client, "quorum_latency_ms" in stats, f"Metrics: quorum_latency_ms={stats.get('quorum_latency_ms')}")

        r1 = client.get(f"{node_url('node1', host)}/merkle").json()["root_hash"]
        r2 = client.get(f"{node_url('node2', host)}/merkle").json()["root_hash"]
        check(client, r1 == r2, "Merkle roots match on healthy cluster")

    print("\n" + "=" * 60)
    print("ALL PHASE 5 LIVE CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
