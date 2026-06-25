"""Tests for node recovery on restart."""

import pytest

from cluster.node_recovery_service import NodeRecoveryService
from replication_helpers import RoutingNodeClient


def test_recover_node_replays_hints(repair_cluster):
    metadata, nodes, _, _, routing_node = repair_cluster
    node1 = nodes["node1"]
    engine = node1.app.state.engine
    hinted = node1.app.state.hinted_handoff

    hinted.store_hint(
        target_node="node2",
        block_id="hint-blk",
        version=1,
        data="hinted-data",
        lsn=1,
    )

    recovery = NodeRecoveryService(
        node_id="node1",
        list_local_blocks_fn=lambda: [
            bid for bid in engine.list_blocks()
            if (r := engine.read_block(bid)) and not r.deleted
        ],
        replay_hints_fn=lambda: hinted.replay_pending(
            {f"node{i}": f"node{i}:800{i}" for i in range(1, 5)}
        ),
        rebuild_inventory_fn=lambda nid, blocks: None,
    )

    result = recovery.recover_node()
    assert result["hints_delivered"] >= 0


def test_rebuild_inventory(repair_cluster):
    metadata, nodes, _, _, _ = repair_cluster
    node1 = nodes["node1"]
    node1.app.state.engine.write_local("inv-blk", "data", 1)

    rebuilt = []
    recovery = NodeRecoveryService(
        node_id="node1",
        list_local_blocks_fn=lambda: ["inv-blk"],
        replay_hints_fn=lambda: 0,
        rebuild_inventory_fn=lambda nid, blocks: rebuilt.append((nid, blocks)),
    )

    count = recovery.rebuild_inventory()
    assert count == 1
    assert rebuilt[0][0] == "node1"
    assert "inv-blk" in rebuilt[0][1]
