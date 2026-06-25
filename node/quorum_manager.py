"""Tracks acknowledgements and evaluates quorum outcomes."""

import time
from enum import Enum
from typing import List, Optional, Set

from node.consistency import ConsistencyLevel
from node.quorum import is_quorum_satisfied, required_acks


class QuorumOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class QuorumManager:

    def __init__(
        self,
        replication_factor: int,
        consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
        timeout_sec: float = 5.0,
    ):
        self._rf = replication_factor
        self._consistency = consistency
        self._timeout_sec = timeout_sec
        self._required = required_acks(replication_factor, consistency)
        self._acked_nodes: Set[str] = set()
        self._failed_nodes: Set[str] = set()
        self._start_time = time.perf_counter()

    @property
    def replication_factor(self) -> int:
        return self._rf

    @property
    def required_acks(self) -> int:
        return self._required

    @property
    def ack_count(self) -> int:
        return len(self._acked_nodes)

    @property
    def failure_count(self) -> int:
        return len(self._failed_nodes)

    @property
    def acked_nodes(self) -> List[str]:
        return sorted(self._acked_nodes)

    @property
    def failed_nodes(self) -> List[str]:
        return sorted(self._failed_nodes)

    def record_ack(self, node_id: str) -> None:
        self._failed_nodes.discard(node_id)
        self._acked_nodes.add(node_id)

    def record_failure(self, node_id: str) -> None:
        if node_id not in self._acked_nodes:
            self._failed_nodes.add(node_id)

    def is_timed_out(self) -> bool:
        elapsed = time.perf_counter() - self._start_time
        return elapsed >= self._timeout_sec

    def evaluate(self) -> QuorumOutcome:
        if is_quorum_satisfied(self.ack_count, self._required):
            return QuorumOutcome.SUCCESS
        if self.is_timed_out():
            return QuorumOutcome.TIMEOUT
        remaining = self._rf - self.ack_count - self.failure_count
        max_possible = self.ack_count + remaining
        if max_possible < self._required:
            return QuorumOutcome.FAILED
        return QuorumOutcome.FAILED

    def latency_ms(self) -> float:
        return (time.perf_counter() - self._start_time) * 1000

    def snapshot(self) -> dict:
        return {
            "replication_factor": self._rf,
            "consistency": self._consistency.value,
            "required_acks": self._required,
            "ack_count": self.ack_count,
            "failure_count": self.failure_count,
            "acked_nodes": self.acked_nodes,
            "failed_nodes": self.failed_nodes,
            "outcome": self.evaluate().value,
            "latency_ms": round(self.latency_ms(), 3),
        }
