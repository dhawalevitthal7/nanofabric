"""Snapshot scheduler — hourly, daily, weekly with retention."""

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from storage.models import PolicySchedule, SnapshotPolicy
from storage.retention_manager import RetentionManager
from storage.snapshot_manager import SnapshotManager
from storage.snapshot_store import SnapshotStore

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


_SCHEDULE_SECONDS = {
    PolicySchedule.HOURLY: 3600,
    PolicySchedule.DAILY: 86400,
    PolicySchedule.WEEKLY: 604800,
}


class SnapshotScheduler:
    """Background scheduler for snapshot policies."""

    def __init__(
        self,
        store: SnapshotStore,
        snapshot_manager: SnapshotManager,
        retention_manager: RetentionManager,
        poll_interval_sec: float = 5.0,
    ):
        self._store = store
        self._snapshot_manager = snapshot_manager
        self._retention = retention_manager
        self._poll_interval = poll_interval_sec
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def create_policy(
        self,
        name: str,
        schedule: PolicySchedule,
        retention_count: int = 7,
        enabled: bool = True,
    ) -> SnapshotPolicy:
        policy = SnapshotPolicy(
            policy_id=str(uuid.uuid4()),
            name=name,
            schedule=schedule,
            retention_count=retention_count,
            enabled=enabled,
            next_run_at=_now_ms(),
        )
        self._store.save_policy(policy)
        return policy

    def list_policies(self):
        return self._store.list_policies()

    def _compute_next_run(self, schedule: PolicySchedule, from_ms: int) -> int:
        delta_sec = _SCHEDULE_SECONDS[schedule]
        return from_ms + delta_sec * 1000

    def run_due_policies(self) -> list:
        now = _now_ms()
        results = []
        for policy in self._store.list_policies():
            if not policy.enabled:
                continue
            if policy.next_run_at and policy.next_run_at > now:
                continue
            try:
                snapshot = self._snapshot_manager.create_snapshot()
                policy.last_run_at = now
                policy.next_run_at = self._compute_next_run(policy.schedule, now)
                self._store.save_policy(policy)
                expired = self._retention.enforce_retention(policy.retention_count)
                results.append(
                    {
                        "policy_id": policy.policy_id,
                        "snapshot_id": snapshot.snapshot_id,
                        "expired": expired,
                    }
                )
                log.info(
                    "scheduled snapshot created",
                    extra={"policy": policy.name, "snapshot": snapshot.snapshot_id},
                )
            except Exception:
                log.exception("scheduled snapshot failed", extra={"policy": policy.name})
        return results

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due_policies()
            except Exception:
                log.exception("scheduler loop error")
            self._stop.wait(self._poll_interval)
