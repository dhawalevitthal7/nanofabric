"""Tests for placement policies."""

import pytest

from metadata.placement_policy import RoundRobinPlacementPolicy


NODES = ["node1", "node2", "node3"]


def test_round_robin_rf1():
    policy = RoundRobinPlacementPolicy()

    assert policy.select_nodes(NODES, 1) == ["node1"]
    assert policy.select_nodes(NODES, 1) == ["node2"]
    assert policy.select_nodes(NODES, 1) == ["node3"]
    assert policy.select_nodes(NODES, 1) == ["node1"]


def test_round_robin_rf2():
    policy = RoundRobinPlacementPolicy()

    assert policy.select_nodes(NODES, 2) == ["node1", "node2"]
    assert policy.select_nodes(NODES, 2) == ["node2", "node3"]
    assert policy.select_nodes(NODES, 2) == ["node3", "node1"]
    assert policy.select_nodes(NODES, 2) == ["node1", "node2"]


def test_round_robin_rf3():
    policy = RoundRobinPlacementPolicy()

    assert policy.select_nodes(NODES, 3) == ["node1", "node2", "node3"]
    assert policy.select_nodes(NODES, 3) == ["node2", "node3", "node1"]
    assert policy.select_nodes(NODES, 3) == ["node3", "node1", "node2"]
    assert policy.select_nodes(NODES, 3) == ["node1", "node2", "node3"]


def test_no_available_nodes():
    policy = RoundRobinPlacementPolicy()
    with pytest.raises(ValueError, match="No available nodes"):
        policy.select_nodes([], 1)


def test_rf_exceeds_nodes():
    policy = RoundRobinPlacementPolicy()
    with pytest.raises(ValueError, match="exceeds"):
        policy.select_nodes(["node1"], 2)
