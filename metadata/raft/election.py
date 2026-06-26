"""Raft leader election helpers."""

import random
from typing import Tuple


def random_election_timeout_ms(min_ms: int = 150, max_ms: int = 300) -> float:
    """Return a randomized election timeout in seconds."""
    return random.randint(min_ms, max_ms) / 1000.0


def is_log_up_to_date(
    candidate_last_index: int,
    candidate_last_term: int,
    our_last_index: int,
    our_last_term: int,
) -> bool:
    """Raft §5.4.1 — candidate log must be at least as up-to-date as receiver."""
    if candidate_last_term != our_last_term:
        return candidate_last_term > our_last_term
    return candidate_last_index >= our_last_index


def majority_count(peer_count: int) -> int:
    """Votes needed including self."""
    return (peer_count + 1) // 2 + 1
