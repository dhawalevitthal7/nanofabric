"""Repair-specific metrics for self-healing observability."""

import threading


class RepairMetrics:

    def __init__(self):
        self._lock = threading.Lock()
        self.repair_jobs_total = 0
        self.repair_jobs_failed = 0
        self.repair_jobs_completed = 0
        self.blocks_rebuilt = 0
        self.under_replicated_blocks = 0
        self.over_replicated_blocks = 0
        self.anti_entropy_repairs = 0
        self.orphan_blocks = 0
        self.repair_latency_ms_total = 0.0
        self.repair_latency_count = 0

    def inc_repair_jobs_total(self):
        with self._lock:
            self.repair_jobs_total += 1

    def inc_repair_jobs_failed(self):
        with self._lock:
            self.repair_jobs_failed += 1

    def inc_repair_jobs_completed(self):
        with self._lock:
            self.repair_jobs_completed += 1

    def inc_blocks_rebuilt(self):
        with self._lock:
            self.blocks_rebuilt += 1

    def inc_anti_entropy_repairs(self):
        with self._lock:
            self.anti_entropy_repairs += 1

    def set_under_replicated_blocks(self, count: int):
        with self._lock:
            self.under_replicated_blocks = count

    def set_over_replicated_blocks(self, count: int):
        with self._lock:
            self.over_replicated_blocks = count

    def set_orphan_blocks(self, count: int):
        with self._lock:
            self.orphan_blocks = count

    def record_repair_latency(self, duration_ms: float):
        with self._lock:
            self.repair_latency_ms_total += duration_ms
            self.repair_latency_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "repair_jobs_total": self.repair_jobs_total,
                "repair_jobs_failed": self.repair_jobs_failed,
                "repair_jobs_completed": self.repair_jobs_completed,
                "blocks_rebuilt": self.blocks_rebuilt,
                "under_replicated_blocks": self.under_replicated_blocks,
                "over_replicated_blocks": self.over_replicated_blocks,
                "anti_entropy_repairs": self.anti_entropy_repairs,
                "orphan_blocks": self.orphan_blocks,
                "repair_latency_ms": (
                    round(
                        self.repair_latency_ms_total / self.repair_latency_count,
                        3,
                    )
                    if self.repair_latency_count
                    else 0.0
                ),
            }
