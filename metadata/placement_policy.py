"""Placement policy engine — decides where new blocks are stored."""

from abc import ABC, abstractmethod
from typing import List


class PlacementPolicy(ABC):
    """Interface for block placement algorithms."""

    @abstractmethod
    def select_nodes(
        self,
        available_nodes: List[str],
        replication_factor: int,
    ) -> List[str]:
        """Return *replication_factor* distinct nodes from *available_nodes*."""


class RoundRobinPlacementPolicy(PlacementPolicy):
    """Round-robin primary selection with consecutive replica placement."""

    def __init__(self) -> None:
        self._counter = 0

    def select_nodes(
        self,
        available_nodes: List[str],
        replication_factor: int,
    ) -> List[str]:
        if not available_nodes:
            raise ValueError("No available nodes for placement")
        if replication_factor < 1:
            raise ValueError("replication_factor must be at least 1")
        if replication_factor > len(available_nodes):
            raise ValueError(
                f"replication_factor ({replication_factor}) exceeds "
                f"available nodes ({len(available_nodes)})"
            )

        sorted_nodes = sorted(available_nodes)
        start = self._counter % len(sorted_nodes)
        self._counter += 1

        selected: List[str] = []
        for offset in range(replication_factor):
            selected.append(sorted_nodes[(start + offset) % len(sorted_nodes)])
        return selected

    def reset(self) -> None:
        """Reset round-robin counter (used after recovery)."""
        self._counter = 0

    def advance(self, steps: int) -> None:
        """Advance counter to match number of already-placed blocks."""
        self._counter = steps
