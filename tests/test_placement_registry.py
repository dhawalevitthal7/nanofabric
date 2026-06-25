"""Tests for the placement registry."""

from metadata.placement_registry import PlacementRegistry


def test_register_and_lookup():
    registry = PlacementRegistry()
    registry.register_block("invoice-1", version=1, nodes=["node1", "node2"])

    assert registry.get_block_locations("invoice-1") == ["node1", "node2"]
    assert registry.get_block_version("invoice-1") == 1
    assert registry.block_exists("invoice-1")


def test_delete_block():
    registry = PlacementRegistry()
    registry.register_block("invoice-1", version=1, nodes=["node1"])

    assert registry.delete_block("invoice-1") is True
    assert registry.delete_block("invoice-1") is False
    assert not registry.block_exists("invoice-1")
    assert registry.get_block_locations("invoice-1") is None


def test_get_node_blocks():
    registry = PlacementRegistry()
    registry.register_block("invoice-1", version=1, nodes=["node1", "node2"])
    registry.register_block("invoice-2", version=1, nodes=["node2", "node3"])

    assert registry.get_node_blocks("node1") == ["invoice-1"]
    assert registry.get_node_blocks("node2") == ["invoice-1", "invoice-2"]
    assert registry.get_node_blocks("node3") == ["invoice-2"]
    assert registry.get_node_blocks("missing") == []


def test_list_all_blocks():
    registry = PlacementRegistry()
    registry.register_block("invoice-1", version=1, nodes=["node1"])
    registry.register_block("invoice-2", version=1, nodes=["node2"])

    assert registry.list_all_blocks() == {
        "invoice-1": ["node1"],
        "invoice-2": ["node2"],
    }


def test_load_from_snapshot():
    registry = PlacementRegistry()
    registry.load_from_snapshot(
        {"invoice-1": ["node1", "node2"]},
        versions={"invoice-1": 2},
    )

    assert registry.get_block_locations("invoice-1") == ["node1", "node2"]
    assert registry.get_block_version("invoice-1") == 2
