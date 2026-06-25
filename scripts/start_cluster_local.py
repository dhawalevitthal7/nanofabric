#!/usr/bin/env python3
"""Start metadata + 3 storage nodes locally (no Docker required).

Usage:
    python scripts/start_cluster_local.py

Then in another terminal:
    python scripts/test_phase4_live.py

If metadata is already running on :9000, only the 3 nodes are started.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
METADATA_PORT = 9000
METADATA_URL = f"http://localhost:{METADATA_PORT}"
NODES = [
    ("node1", 8001),
    ("node2", 8002),
    ("node3", 8003),
]


def is_healthy(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def wait_for_url(url: str, label: str, timeout_sec: float = 30.0) -> None:
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                print(f"  ready  {label} ({url})")
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {label} at {url}: {last_error}")


def main() -> None:
    data_root = ROOT / "data" / "local-cluster"
    data_root.mkdir(parents=True, exist_ok=True)

    procs: list[subprocess.Popen] = []
    started_metadata = False

    def shutdown(*_args):
        print("\nShutting down cluster...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        if started_metadata:
            print("  stopped metadata (started by this script)")
        else:
            print("  left existing metadata on :9000 running")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("NanoFabric — Local Cluster (no Docker)")
    print("=" * 60)
    print(f"Data directory: {data_root}\n")

    env_base = os.environ.copy()
    env_base["METADATA_DB_PATH"] = str(data_root / "metadata.db")

    metadata_health = f"{METADATA_URL}/health"
    if is_healthy(metadata_health):
        print(f"Metadata already running at {METADATA_URL} — reusing it")
    else:
        print("Starting metadata service...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "metadata.main"],
            cwd=ROOT,
            env={**env_base, "METADATA_PORT": str(METADATA_PORT)},
        )
        procs.append(proc)
        started_metadata = True
        time.sleep(1.0)
        if proc.poll() is not None:
            if is_healthy(metadata_health):
                print("  note: metadata port was in use but service is healthy — reusing")
                started_metadata = False
            else:
                print(
                    f"\nERROR: metadata failed to start (exit {proc.returncode}).\n"
                    "Port 9000 may be in use by another process that is not responding.\n"
                    "Stop the other process or run: netstat -ano | findstr :9000",
                    file=sys.stderr,
                )
                sys.exit(1)

    for node_id, port in NODES:
        health = f"http://localhost:{port}/health"
        if is_healthy(health):
            print(f"  skip  {node_id} already running on :{port}")
            continue
        print(f"Starting {node_id} on port {port}...")
        node_env = {
            **env_base,
            "NODE_ID": node_id,
            "NODE_PORT": str(port),
            "NODE_ADDRESS": f"localhost:{port}",
            "METADATA_URL": METADATA_URL,
            "DATA_DIR": str(data_root / node_id),
        }
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "node.main"],
                cwd=ROOT,
                env=node_env,
            )
        )

    print("\nWaiting for services...")
    try:
        wait_for_url(metadata_health, "metadata")
        for node_id, port in NODES:
            wait_for_url(f"http://localhost:{port}/health", node_id)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        shutdown()
        return

    print("\n" + "=" * 60)
    print("Cluster is running. Press Ctrl+C to stop.")
    print()
    print(f"  Metadata:  {METADATA_URL}/health")
    print("  Node 1:    http://localhost:8001/health")
    print("  Node 2:    http://localhost:8002/health")
    print("  Node 3:    http://localhost:8003/health")
    print()
    print("Run Phase 4 live test (in another terminal):")
    print("  python scripts/test_phase4_live.py")
    print("=" * 60)

    while True:
        time.sleep(2)
        for p in procs:
            if p.poll() is not None:
                print(
                    f"\nERROR: process exited with code {p.returncode}",
                    file=sys.stderr,
                )
                shutdown()
                return


if __name__ == "__main__":
    main()
