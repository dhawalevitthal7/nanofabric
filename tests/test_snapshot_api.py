"""Tests for snapshot/backup HTTP APIs."""

import pytest
from fastapi.testclient import TestClient

from metadata.app import create_app
from node.storage_engine import StorageEngine
from storage.cluster_bridge import EngineBlockAdapter, make_placement_restore
from storage.protection_factory import build_protection_stack
from metadata.metadata_store import MetadataStore


@pytest.fixture
def api_client(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    engine = StorageEngine(tmp_path / "node", node_id="node1")
    adapter = EngineBlockAdapter(engine)

    def clear_blocks():
        engine.purge_all_blocks()

    stack = build_protection_stack(
        data_dir=tmp_path / "protection",
        read_blocks=adapter,
        write_blocks=adapter,
        get_metadata_version=lambda: store.get_stats()["total_blocks"],
        get_placements=store.list_all_placements,
        restore_placement=make_placement_restore(store),
        clear_blocks=clear_blocks,
    )

    app = create_app(db_path=db_path)
    app.state.protection_stack = stack
    app.state.block_bridge = adapter
    app.state.start_repair_worker = False
    app.state.start_protection_scheduler = False

    with TestClient(app) as client:
        yield client, engine, store

    stack.close()
    engine.close()
    store.close()


def test_create_and_list_snapshots(api_client):
    client, engine, store = api_client
    engine.write("api-b1", "hello", version=1)
    store.save_placement("api-b1", 1, ["node1"])

    resp = client.post("/snapshots")
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["block_count"] == 1

    listed = client.get("/snapshots").json()
    assert len(listed) >= 1


def test_restore_snapshot_api(api_client):
    client, engine, store = api_client
    engine.write("api-r1", "before", version=1)
    store.save_placement("api-r1", 1, ["node1"])

    snap = client.post("/snapshots").json()
    engine.write("api-r1", "after", version=2)

    resp = client.post(f"/snapshots/{snap['snapshot_id']}/restore")
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"
    assert engine.read("api-r1") == "before"


def test_delete_snapshot_api(api_client):
    client, engine, _ = api_client
    engine.write("del", "x", version=1)
    snap = client.post("/snapshots").json()

    resp = client.delete(f"/snapshots/{snap['snapshot_id']}")
    assert resp.status_code == 200
    assert client.get("/snapshots").json() == []


def test_backup_and_restore_api(api_client):
    client, engine, store = api_client
    engine.write("bk", "data", version=1)
    store.save_placement("bk", 1, ["node1"])

    backup = client.post("/backups", json={"backup_type": "FULL"}).json()
    assert backup["status"] == "READY"

    engine.write("bk", "changed", version=2)
    resp = client.post(f"/backups/{backup['backup_id']}/restore")
    assert resp.status_code == 200
    assert engine.read("bk") == "data"


def test_snapshot_policy_api(api_client):
    client, engine, _ = api_client
    engine.write("pol", "v", version=1)

    resp = client.post(
        "/snapshot-policies",
        json={"name": "test-policy", "schedule": "daily", "retention_count": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["schedule"] == "daily"

    policies = client.get("/snapshot-policies").json()
    assert len(policies) >= 1


def test_protection_metrics_api(api_client):
    client, engine, _ = api_client
    engine.write("m", "v", version=1)
    client.post("/snapshots")

    metrics = client.get("/protection/metrics").json()
    assert "snapshots_total" in metrics
    assert metrics["snapshots_total"] >= 1
