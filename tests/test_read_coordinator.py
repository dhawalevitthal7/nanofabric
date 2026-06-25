"""Tests for ReadCoordinator."""

from unittest.mock import MagicMock

import pytest

from node.consistency import ConsistencyLevel
from node.metrics import Metrics
from node.read_coordinator import ReadCoordinator
from node.read_repair import ReadRepair
from node.storage_engine import StorageEngine


@pytest.fixture
def coordinator(tmp_path):
    engine = StorageEngine(tmp_path / "node1", node_id="node1")
    metadata = MagicMock()
    metadata.get_block_locations.return_value = ["node1", "node2", "node3"]
    metadata.get_node_addresses.return_value = {
        "node1": "node1:8001",
        "node2": "node2:8002",
        "node3": "node3:8003",
    }
    metadata.resolve_node_url.side_effect = lambda nid, addr: f"http://{addr[nid]}"

    replica_client = MagicMock()
    metrics = Metrics()
    read_repair = ReadRepair("node1", replica_client, metrics, metadata.resolve_node_url)

    engine.write_local("block-1", "hello", version=1)

    def read_remote(url, node_id, block_id):
        if node_id == "node2":
            return {"block_id": block_id, "data": "hello", "version": 1, "origin_lsn": 1}
        if node_id == "node3":
            return {"block_id": block_id, "data": "stale", "version": 1, "origin_lsn": 0}
        return None

    replica_client.read_block.side_effect = read_remote

    coord = ReadCoordinator(
        node_id="node1",
        engine=engine,
        metadata_client=metadata,
        replica_client=replica_client,
        read_repair=read_repair,
        metrics=metrics,
        consistency=ConsistencyLevel.QUORUM,
    )
    yield coord, engine, read_repair, metrics
    engine.close()
    read_repair.shutdown()


def test_read_quorum_returns_latest(coordinator):
    coord, engine, *_ = coordinator
    result = coord.read("block-1", repair=False)
    assert result is not None
    assert result.quorum_satisfied is True
    assert result.data == "hello"
    assert result.copies_read >= 2


def test_quorum_status(coordinator):
    coord, *_ = coordinator
    status = coord.get_quorum_status("block-1")
    assert status["replication_factor"] == 3
    assert status["write_quorum"] == 2
    assert status["read_quorum"] == 2
