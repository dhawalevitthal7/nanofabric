"""Raft log compaction and snapshot management."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metadata.raft.node import RaftNode
    from metadata.raft.state_machine import RaftStateMachine
    from metadata.raft.storage import RaftStorage

log = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_THRESHOLD = 50


class SnapshotManager:
    """Creates and restores Raft snapshots."""

    def __init__(
        self,
        storage: "RaftStorage",
        state_machine: "RaftStateMachine",
        threshold: int = DEFAULT_SNAPSHOT_THRESHOLD,
    ) -> None:
        self._storage = storage
        self._state_machine = state_machine
        self._threshold = threshold

    def maybe_snapshot(self, node: "RaftNode") -> None:
        log_len = len(node.log)
        if log_len < self._threshold:
            return
        if node.last_applied <= node.snapshot_index:
            return

        data = self._state_machine.build_snapshot()
        self._storage.save_snapshot(node.last_applied, node.log_term_at(node.last_applied), data)
        node.on_snapshot_created(node.last_applied)

    def restore(self, node: "RaftNode") -> int:
        last_index, last_term, data = self._storage.get_snapshot()
        if last_index == 0:
            return 0

        self._state_machine.restore_snapshot(data)
        node.on_snapshot_restored(last_index, last_term)
        log.info("restored snapshot", extra={"last_index": last_index})
        return last_index
