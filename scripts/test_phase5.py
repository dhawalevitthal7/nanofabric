#!/usr/bin/env python3
"""Phase 5 integration smoke test — quorum, consistency, hints, read repair."""

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
from node.replica_client import ReplicaClientError
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


class SelectiveFailClient:
    """Replica client that fails writes to specific nodes."""

    def __init__(self, inner, down_nodes=None):
        self._inner = inner
        self._down_nodes = set(down_nodes or [])

    def replicate_write(self, target_url, target_node, request):
        if target_node in self._down_nodes:
            raise ReplicaClientError(target_node, "down")
        return self._inner.replicate_write(target_url, target_node, request)

    def replicate_delete(self, target_url, target_node, request):
        if target_node in self._down_nodes:
            raise ReplicaClientError(target_node, "down")
        return self._inner.replicate_delete(target_url, target_node, request)

    def read_block(self, target_url, target_node, block_id):
        return self._inner.read_block(target_url, target_node, block_id)


def set_replica_client(nodes, client) -> None:
    for tc in nodes.values():
        tc.app.state.config["replica_client"] = client
        tc.app.state.replication_service._replica_client = client


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
            start_hint_worker=False,
        )
        tc = TestClient(app)
        tc.__enter__()
        node_clients[node_id] = tc

    return metadata, node_clients, routing


def teardown_cluster(metadata, node_clients) -> None:
    for tc in node_clients.values():
        tc.__exit__(None, None, None)
    metadata.__exit__(None, None, None)


def main() -> None:
    print("=" * 60)
    print("NanoFabric Phase 5 — Quorum & Consistency Smoke Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        metadata, nodes, routing = build_cluster(tmp_path)
        block_id = "invoice-123"

        try:
            print("\n[1] Allocate block with RF=3...")
            r = metadata.post("/allocate", json={"block_id": block_id, "rf": 3})
            check(r.status_code == 200, "Allocate RF=3")

            print("\n[2] Quorum status endpoint...")
            r = nodes["node1"].get("/quorum/status", params={"block_id": block_id})
            check(r.status_code == 200, "GET /quorum/status")
            body = r.json()
            check(body["write_quorum"] == 2, f"W=2 (got {body['write_quorum']})")
            check(body["read_quorum"] == 2, f"R=2 (got {body['read_quorum']})")

            print("\n[3] Scenario 1 — 1 replica down, write succeeds (W=2)...")
            set_replica_client(nodes, SelectiveFailClient(routing, down_nodes={"node3"}))
            r = nodes["node1"].post("/write", json={"block_id": block_id, "data": "hello"})
            check(r.status_code == 200, "Write with 1 replica down")
            check(r.json()["ok"] is True, "Write ok=true")
            quorum = r.json().get("quorum", {})
            check(quorum.get("quorum_satisfied") is True, f"Quorum satisfied: {quorum}")
            check(quorum.get("ack_count", 0) >= 2, f"acks={quorum.get('ack_count')}")

            pending = nodes["node1"].get("/hints/pending").json()
            check(len(pending) >= 1, f"Hint created for down replica ({len(pending)} pending)")

            print("\n[4] Read quorum succeeds with 2 copies...")
            r = nodes["node1"].post("/read-quorum", json={"block_id": block_id})
            check(r.status_code == 200, "POST /read-quorum")
            check(r.json()["data"] == "hello", f"Data: {r.json()['data']!r}")

            print("\n[5] Scenario 2 — 2 replicas down, write fails...")
            set_replica_client(nodes, SelectiveFailClient(routing, down_nodes={"node2", "node3"}))
            r = nodes["node1"].post("/write", json={"block_id": block_id, "data": "fail-write"})
            check(r.status_code == 503, f"Write fails with 503 (got {r.status_code})")

            print("\n[6] Scenario 3 — hint replay on recovery...")
            hint_block = "hint-replay-block"
            metadata.post("/allocate", json={"block_id": hint_block, "rf": 3})
            set_replica_client(nodes, SelectiveFailClient(routing, down_nodes={"node3"}))
            r = nodes["node1"].post("/write", json={"block_id": hint_block, "data": "hinted-data"})
            check(r.status_code == 200, "Write with node3 down (fresh block)")

            set_replica_client(nodes, routing)
            r = nodes["node1"].post("/hints/replay")
            check(r.status_code == 200, "POST /hints/replay")
            delivered = r.json().get("delivered", 0)
            check(delivered >= 1, f"Delivered {delivered} hint(s)")

            r = nodes["node3"].get(f"/read/{hint_block}")
            check(r.status_code == 200, "node3 has data after hint replay")
            check(r.json()["data"] == "hinted-data", f"node3 data: {r.json()['data']!r}")

            print("\n[7] Scenario 4 — read repair restores stale replica...")
            repair_block = "repair-block"
            metadata.post("/allocate", json={"block_id": repair_block, "rf": 3})
            set_replica_client(nodes, routing)
            nodes["node1"].post("/write", json={"block_id": repair_block, "data": "v1"})

            set_replica_client(nodes, SelectiveFailClient(routing, down_nodes={"node2"}))
            nodes["node1"].post("/write", json={"block_id": repair_block, "data": "v2"})

            r = nodes["node2"].get(f"/read/{repair_block}")
            check(r.json()["data"] == "v1", "node2 still stale (v1)")

            set_replica_client(nodes, routing)
            r = nodes["node1"].post("/repair", json={"block_id": repair_block})
            check(r.status_code == 200, "POST /repair")
            check(r.json().get("repaired", 0) >= 1, f"Repaired {r.json().get('repaired')} replica(s)")

            r = nodes["node2"].get(f"/read/{repair_block}")
            check(r.json()["data"] == "v2", "node2 repaired to v2")

            print("\n[8] Scenario 5 — merkle trees differ on divergence...")
            nodes["node2"].post(
                "/replicate",
                json={
                    "block_id": "merkle-test",
                    "data": "diverged",
                    "version": 5,
                    "lsn": 99,
                    "origin_node_id": "node1",
                },
            )
            nodes["node1"].post("/write", json={"block_id": "merkle-test", "data": "canonical"})

            root1 = nodes["node1"].get("/merkle").json()["root_hash"]
            root2 = nodes["node2"].get("/merkle").json()["root_hash"]
            check(root1 != root2, "Merkle roots differ on diverged replicas")

            print("\n[9] Consistency level API...")
            r = nodes["node1"].get("/consistency")
            check(r.json()["level"] == "QUORUM", "Default QUORUM")
            nodes["node1"].post("/consistency", json={"level": "ONE"})
            check(nodes["node1"].get("/consistency").json()["level"] == "ONE", "Set ONE")

            print("\n[10] Replication consistency + metrics...")
            r = nodes["node1"].get("/replication/consistency", params={"block_id": block_id})
            check(r.status_code == 200, "GET /replication/consistency")
            stats = nodes["node1"].get("/replication/stats").json()
            check("write_quorum_failures" in stats, "write_quorum_failures metric present")
            check("read_repairs" in stats, "read_repairs metric present")
            check("hint_deliveries" in stats, "hint_deliveries metric present")

        finally:
            teardown_cluster(metadata, nodes)

    print("\n" + "=" * 60)
    print("ALL PHASE 5 INTEGRATION CHECKS PASSED")
    print("Quorum writes, read repair, hinted handoff, and merkle — verified.")
    print("=" * 60)


if __name__ == "__main__":
    main()
