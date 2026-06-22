"""Authoritative in-memory cluster membership registry."""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from metadata.constants import FAILURE_TIMEOUT_SEC, NODE_STATUS_DOWN, NODE_STATUS_UP
from metadata.models import NodeRecord, NodeStatus

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class MembershipRegistry:
    """Maintains cluster membership, heartbeats, and node lifecycle state."""

    def __init__(self, failure_timeout_sec: float = FAILURE_TIMEOUT_SEC):
        self._lock = threading.Lock()
        self._nodes: Dict[str, NodeRecord] = {}
        self._failure_timeout_ms = int(failure_timeout_sec * 1000)

    def register(self, node_id: str, address: str) -> NodeRecord:
        now = _now_ms()
        with self._lock:
            existing = self._nodes.get(node_id)
            if existing:
                record = existing.model_copy(
                    update={
                        "address": address,
                        "status": NodeStatus.UP,
                        "last_seen": now,
                        "recovered_at": now if existing.status == NodeStatus.DOWN else existing.recovered_at,
                        "failed_at": None,
                    }
                )
                log.info("node re-registered", extra={"node_id": node_id, "address": address})
            else:
                record = NodeRecord(
                    node_id=node_id,
                    status=NodeStatus.UP,
                    address=address,
                    last_seen=now,
                    registered_at=now,
                )
                log.info("node registered", extra={"node_id": node_id, "address": address})
            self._nodes[node_id] = record
            return record.model_copy()

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            log.info("node removed", extra={"node_id": node_id})
            return True

    def heartbeat(self, node_id: str, timestamp: Optional[int] = None) -> NodeRecord:
        now = timestamp if timestamp is not None else _now_ms()
        with self._lock:
            record = self._nodes.get(node_id)
            if record is None:
                raise KeyError(f"Node '{node_id}' is not registered")

            was_down = record.status == NodeStatus.DOWN
            record = record.model_copy(
                update={
                    "status": NodeStatus.UP,
                    "last_seen": now,
                    "failed_at": None,
                    "recovered_at": now if was_down else record.recovered_at,
                }
            )
            self._nodes[node_id] = record
            if was_down:
                log.info("node recovered", extra={"node_id": node_id})
            return record.model_copy()

    def check_failures(self, now_ms: Optional[int] = None) -> List[Tuple[str, str]]:
        """Mark stale nodes DOWN. Returns (node_id, transition) pairs."""
        now = now_ms if now_ms is not None else _now_ms()
        transitions: List[Tuple[str, str]] = []

        with self._lock:
            for node_id, record in self._nodes.items():
                if record.status == NodeStatus.DOWN:
                    continue
                if now - record.last_seen > self._failure_timeout_ms:
                    updated = record.model_copy(
                        update={
                            "status": NodeStatus.DOWN,
                            "failed_at": now,
                        }
                    )
                    self._nodes[node_id] = updated
                    transitions.append((node_id, "DOWN"))
                    log.warning(
                        "node marked DOWN",
                        extra={"node_id": node_id, "last_seen": record.last_seen},
                    )
        return transitions

    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        with self._lock:
            record = self._nodes.get(node_id)
            return record.model_copy() if record else None

    def get_all_nodes(self) -> Dict[str, NodeRecord]:
        with self._lock:
            return {node_id: record.model_copy() for node_id, record in self._nodes.items()}

    def get_cluster_summary(self) -> Dict[str, str]:
        with self._lock:
            return {node_id: record.status.value for node_id, record in self._nodes.items()}
