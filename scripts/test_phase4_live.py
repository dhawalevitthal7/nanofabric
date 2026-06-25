#!/usr/bin/env python3
"""Live Phase 4 smoke test — single write, automatic replication to replicas.

Prerequisites:
  - Metadata on :9000 and nodes on :8001-:8003 must be running.

  Without Docker (recommended on Windows):
    Terminal 1:  python scripts/start_cluster_local.py
    Terminal 2:  python scripts/test_phase4_live.py

  With Docker:
    docker compose up --build
    python scripts/test_phase4_live.py --docker
"""

import argparse
import sys
import time

import httpx

NODE_PORTS = {"node1": 8001, "node2": 8002, "node3": 8003}
BLOCK_ID = "invoice-123"
DATA = "hello"


def node_url(node_id: str, host: str = "localhost") -> str:
    return f"http://{host}:{NODE_PORTS[node_id]}"


def node_address(node_id: str, host: str) -> str:
    return f"{host}:{NODE_PORTS[node_id]}"


def check_service(client: httpx.Client, url: str, label: str) -> None:
    try:
        r = client.get(url)
        if r.status_code == 200:
            print(f"  OK    {label}")
            return
        print(f"  FAIL  {label} — HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        print(f"  FAIL  {label} — {exc}")
    print(
        f"\nERROR: {label} is not reachable at {url}\n"
        "\nStart the cluster first:\n"
        "  python scripts/start_cluster_local.py     (no Docker)\n"
        "  docker compose up --build                 (with Docker)\n"
    )
    sys.exit(1)


def preflight(client: httpx.Client, metadata: str, host: str) -> None:
    print("Preflight — checking services...\n")
    check_service(client, f"{metadata}/health", "metadata")
    for node_id in NODE_PORTS:
        check_service(client, node_url(node_id, host).replace("/health", "") + "/health", node_id)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 live replication test")
    parser.add_argument(
        "metadata",
        nargs="?",
        default="http://localhost:9000",
        help="Metadata service URL (default: http://localhost:9000)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Use Docker-style hostnames (node1:8001) for node registration",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for node HTTP URLs (default: localhost, or node id prefix with --docker)",
    )
    args = parser.parse_args()

    metadata = args.metadata.rstrip("/")
    if args.host:
        host = args.host
    elif args.docker:
        host = None  # use per-node hostname
    else:
        host = "localhost"

    addr_host = host if host else "node"
    print(f"Phase 4 live test — metadata at {metadata}")
    if host:
        print(f"Node host: {host}\n")
    else:
        print("Node host: docker internal (node1, node2, node3)\n")

    with httpx.Client(timeout=10.0) as client:
        preflight(client, metadata, host or "localhost")

        for node_id in NODE_PORTS:
            address = (
                node_address(node_id, host)
                if host
                else f"{node_id}:{NODE_PORTS[node_id]}"
            )
            r = client.post(
                f"{metadata}/register",
                json={"node_id": node_id, "address": address},
            )
            assert r.status_code == 200, f"register {node_id}: {r.status_code} {r.text}"
        print("  PASS  register 3 nodes (localhost addresses)")

        for node_id in NODE_PORTS:
            r = client.post(f"{metadata}/heartbeat", json={"node_id": node_id})
            assert r.status_code == 200
        print("  PASS  heartbeat all nodes")

        r = client.post(f"{metadata}/allocate", json={"block_id": BLOCK_ID, "rf": 3})
        if r.status_code == 409:
            loc = client.get(f"{metadata}/blocks/{BLOCK_ID}").json()["locations"]
            print(f"  PASS  allocate skipped (409) — using existing placement {loc}")
        else:
            assert r.status_code == 200, f"allocate failed: {r.status_code} {r.text}"
            print(f"  PASS  allocate {BLOCK_ID} -> {r.json()['nodes']}")

        locations = client.get(f"{metadata}/blocks/{BLOCK_ID}").json()["locations"]
        assert len(locations) == 3, f"expected RF=3, got {locations}"
        primary = locations[0]
        replicas = [n for n in locations if n != primary]

        def url_for(node_id: str) -> str:
            if host:
                return node_url(node_id, host)
            return node_url(node_id, node_id)

        print(f"  PASS  placement: primary={primary}, replicas={replicas}")

        r = client.post(
            f"{url_for(primary)}/write",
            json={"block_id": BLOCK_ID, "data": DATA},
        )
        assert r.status_code == 200, f"write failed: {r.status_code} {r.text}"
        print(f"  PASS  single write to {primary}: {r.json()}")

        time.sleep(0.5)

        read_primary = client.get(f"{url_for(primary)}/read/{BLOCK_ID}")
        assert read_primary.status_code == 200
        assert read_primary.json()["data"] == DATA
        print(f"  PASS  read primary ({primary}): {read_primary.json()['data']!r}")

        for replica in replicas:
            r = client.get(f"{url_for(replica)}/read/{BLOCK_ID}")
            assert r.status_code == 200, f"replica {replica} read failed: {r.status_code} {r.text}"
            assert r.json()["data"] == DATA, f"replica {replica} data mismatch: {r.json()}"
            print(f"  PASS  read replica ({replica}): {r.json()['data']!r}")

        state = client.get(f"{url_for(primary)}/replication/state/{BLOCK_ID}")
        assert state.status_code == 200, f"replication state: {state.status_code} {state.text}"
        assert state.json()["state"] == "REPLICATED"
        print(f"  PASS  replication state: {state.json()['state']}")

        stats = client.get(f"{url_for(primary)}/replication/stats").json()
        assert stats["successful_replications"] >= len(replicas)
        print(f"  PASS  replication stats: {stats}")

    print("\nALL PHASE 4 LIVE CHECKS PASSED")
    print("Client performed ONE write — replicas received data automatically.")


if __name__ == "__main__":
    main()
