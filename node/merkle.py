"""Merkle tree for anti-entropy block comparison."""

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def _hash_pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}{right}".encode()).hexdigest()


def _hash_leaf(block_id: str, data: str, version: int) -> str:
    content = f"{block_id}:{version}:{data}"
    return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class MerkleNode:
    hash_value: str
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    block_id: Optional[str] = None


class MerkleTree:

    def __init__(self, blocks: Dict[str, Tuple[str, int]]):
        """blocks: block_id -> (data, version)"""
        self._blocks = dict(blocks)
        self._leaves: List[MerkleNode] = []
        self._root: Optional[MerkleNode] = None
        self._build()

    @property
    def root_hash(self) -> str:
        return self._root.hash_value if self._root else ""

    @property
    def block_count(self) -> int:
        return len(self._blocks)

    def _build(self) -> None:
        sorted_ids = sorted(self._blocks.keys())
        if not sorted_ids:
            self._root = MerkleNode(hash_value=_hash_pair("", ""))
            return

        self._leaves = [
            MerkleNode(
                hash_value=_hash_leaf(bid, self._blocks[bid][0], self._blocks[bid][1]),
                block_id=bid,
            )
            for bid in sorted_ids
        ]
        self._root = self._build_level(self._leaves)

    def _build_level(self, nodes: List[MerkleNode]) -> MerkleNode:
        if len(nodes) == 1:
            return nodes[0]
        next_level: List[MerkleNode] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            parent = MerkleNode(
                hash_value=_hash_pair(left.hash_value, right.hash_value),
                left=left,
                right=right,
            )
            next_level.append(parent)
        return self._build_level(next_level)

    def leaf_hashes(self) -> Dict[str, str]:
        return {leaf.block_id: leaf.hash_value for leaf in self._leaves if leaf.block_id}


def compare_trees(tree_a: MerkleTree, tree_b: MerkleTree) -> List[str]:
    """Return block_ids that differ between two merkle trees."""
    hashes_a = tree_a.leaf_hashes()
    hashes_b = tree_b.leaf_hashes()
    all_ids = set(hashes_a.keys()) | set(hashes_b.keys())
    return sorted(
        bid for bid in all_ids
        if hashes_a.get(bid) != hashes_b.get(bid)
    )


def trees_match(tree_a: MerkleTree, tree_b: MerkleTree) -> bool:
    return tree_a.root_hash == tree_b.root_hash
