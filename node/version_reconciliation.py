"""Latest-version-wins reconciliation across replica copies."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ReplicaCopy:
    node_id: str
    block_id: str
    data: str
    version: int
    lsn: int = 0
    timestamp_ms: int = 0
    deleted: bool = False


def compare_copies(a: ReplicaCopy, b: ReplicaCopy) -> int:
    """Return positive if a is newer, negative if b is newer, 0 if equal."""
    if a.version != b.version:
        return a.version - b.version
    if a.lsn != b.lsn:
        return a.lsn - b.lsn
    return a.timestamp_ms - b.timestamp_ms


def select_latest(copies: List[ReplicaCopy]) -> Optional[ReplicaCopy]:
    if not copies:
        return None
    latest = copies[0]
    for copy in copies[1:]:
        if compare_copies(copy, latest) > 0:
            latest = copy
    return latest


def find_stale_replicas(
    copies: List[ReplicaCopy],
    latest: ReplicaCopy,
) -> List[ReplicaCopy]:
    return [c for c in copies if compare_copies(c, latest) < 0]
