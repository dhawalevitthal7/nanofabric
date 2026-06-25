"""Tests for Merkle tree anti-entropy foundation."""

from node.merkle import MerkleTree, compare_trees, trees_match


def test_empty_tree():
    tree = MerkleTree({})
    assert tree.block_count == 0
    assert tree.root_hash != ""


def test_identical_trees_match():
    blocks = {"a": ("data-a", 1), "b": ("data-b", 2)}
    tree_a = MerkleTree(blocks)
    tree_b = MerkleTree(blocks)
    assert trees_match(tree_a, tree_b)
    assert compare_trees(tree_a, tree_b) == []


def test_diverged_replicas_detected():
    tree_a = MerkleTree({"a": ("v1", 1), "b": ("same", 1)})
    tree_b = MerkleTree({"a": ("v2", 1), "b": ("same", 1)})
    assert not trees_match(tree_a, tree_b)
    diff = compare_trees(tree_a, tree_b)
    assert "a" in diff


def test_leaf_hashes():
    blocks = {"x": ("hello", 3)}
    tree = MerkleTree(blocks)
    hashes = tree.leaf_hashes()
    assert "x" in hashes
    assert len(hashes["x"]) == 64
