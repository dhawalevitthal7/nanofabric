"""Metrics for data protection operations."""

import threading


class ProtectionMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.snapshots_total = 0
        self.snapshot_size_bytes = 0
        self.backups_total = 0
        self.restore_jobs_total = 0
        self.restore_duration_ms_total = 0.0
        self.restore_duration_count = 0

    def inc_snapshots(self, size_bytes: int = 0):
        with self._lock:
            self.snapshots_total += 1
            self.snapshot_size_bytes += size_bytes

    def dec_snapshots(self, size_bytes: int = 0):
        with self._lock:
            self.snapshots_total = max(0, self.snapshots_total - 1)
            self.snapshot_size_bytes = max(0, self.snapshot_size_bytes - size_bytes)

    def inc_backups(self):
        with self._lock:
            self.backups_total += 1

    def inc_restore_jobs(self, duration_ms: float = 0.0):
        with self._lock:
            self.restore_jobs_total += 1
            if duration_ms > 0:
                self.restore_duration_ms_total += duration_ms
                self.restore_duration_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "snapshots_total": self.snapshots_total,
                "snapshot_size_bytes": self.snapshot_size_bytes,
                "backups_total": self.backups_total,
                "restore_jobs_total": self.restore_jobs_total,
                "restore_duration_ms": (
                    round(
                        self.restore_duration_ms_total / self.restore_duration_count,
                        3,
                    )
                    if self.restore_duration_count
                    else 0.0
                ),
            }
