"""In-memory replication state tracker per block."""

import threading
from typing import Dict, List, Optional

from node.replication_models import BlockReplicationState, ReplicationState


class ReplicaManager:

    def __init__(self):
        self._lock = threading.Lock()
        self._states: Dict[str, BlockReplicationState] = {}

    def mark_pending(
        self, block_id: str, version: int, replicas: List[str]
    ) -> BlockReplicationState:
        with self._lock:
            state = BlockReplicationState(
                block_id=block_id,
                version=version,
                replicas=list(replicas),
                state=ReplicationState.PENDING,
            )
            self._states[block_id] = state
            return state.model_copy()

    def mark_writing(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            if state is None:
                return None
            updated = state.model_copy(update={"state": ReplicationState.WRITING})
            self._states[block_id] = updated
            return updated.model_copy()

    def mark_replicating(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            if state is None:
                return None
            updated = state.model_copy(update={"state": ReplicationState.REPLICATING})
            self._states[block_id] = updated
            return updated.model_copy()

    def mark_replicated(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            if state is None:
                return None
            updated = state.model_copy(update={"state": ReplicationState.REPLICATED})
            self._states[block_id] = updated
            return updated.model_copy()

    def mark_failed(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            if state is None:
                return None
            updated = state.model_copy(update={"state": ReplicationState.FAILED})
            self._states[block_id] = updated
            return updated.model_copy()

    def mark_degraded(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            if state is None:
                return None
            updated = state.model_copy(update={"state": ReplicationState.DEGRADED})
            self._states[block_id] = updated
            return updated.model_copy()

    def get_replica_state(self, block_id: str) -> Optional[BlockReplicationState]:
        with self._lock:
            state = self._states.get(block_id)
            return state.model_copy() if state else None

    def list_failed_replications(self) -> List[BlockReplicationState]:
        with self._lock:
            return [
                state.model_copy()
                for state in self._states.values()
                if state.state in (ReplicationState.FAILED, ReplicationState.DEGRADED)
            ]

    def list_all_states(self) -> List[BlockReplicationState]:
        with self._lock:
            return [state.model_copy() for state in self._states.values()]
