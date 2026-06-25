import threading
import time


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.writes_total = 0
        self.deletes_total = 0
        self.reads_total = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.replay_entries = 0
        self.fsync_count = 0
        self.fsync_ms_total = 0.0
        self.corruption_events = 0
        self.successful_replications = 0
        self.failed_replications = 0
        self.retry_count = 0
        self.replication_latency_ms_total = 0.0
        self.replication_latency_count = 0
        self.degraded_replications = 0
        self.write_quorum_failures = 0
        self.read_quorum_failures = 0
        self.read_repairs = 0
        self.hint_deliveries = 0
        self.hint_failures = 0
        self.quorum_latency_ms_total = 0.0
        self.quorum_latency_count = 0
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

    def inc_writes(self):
        with self._lock:
            self.writes_total += 1

    def inc_deletes(self):
        with self._lock:
            self.deletes_total += 1

    def inc_reads(self, cache_hit=False):
        with self._lock:
            self.reads_total += 1
            if cache_hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def inc_replay(self, count=1):
        with self._lock:
            self.replay_entries += count

    def record_fsync(self, duration_ms):
        with self._lock:
            self.fsync_count += 1
            self.fsync_ms_total += duration_ms

    def inc_corruption(self):
        with self._lock:
            self.corruption_events += 1

    def inc_successful_replications(self):
        with self._lock:
            self.successful_replications += 1

    def inc_failed_replications(self):
        with self._lock:
            self.failed_replications += 1

    def inc_replication_retries(self):
        with self._lock:
            self.retry_count += 1

    def inc_degraded_replications(self):
        with self._lock:
            self.degraded_replications += 1

    def inc_write_quorum_failures(self):
        with self._lock:
            self.write_quorum_failures += 1

    def inc_read_quorum_failures(self):
        with self._lock:
            self.read_quorum_failures += 1

    def inc_read_repairs(self):
        with self._lock:
            self.read_repairs += 1

    def inc_hint_deliveries(self):
        with self._lock:
            self.hint_deliveries += 1

    def inc_hint_failures(self):
        with self._lock:
            self.hint_failures += 1

    def record_quorum_latency(self, duration_ms):
        with self._lock:
            self.quorum_latency_ms_total += duration_ms
            self.quorum_latency_count += 1

    def record_replication_latency(self, duration_ms):
        with self._lock:
            self.replication_latency_ms_total += duration_ms
            self.replication_latency_count += 1

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

    def set_under_replicated_blocks(self, count):
        with self._lock:
            self.under_replicated_blocks = count

    def set_over_replicated_blocks(self, count):
        with self._lock:
            self.over_replicated_blocks = count

    def set_orphan_blocks(self, count):
        with self._lock:
            self.orphan_blocks = count

    def record_repair_latency(self, duration_ms):
        with self._lock:
            self.repair_latency_ms_total += duration_ms
            self.repair_latency_count += 1

    def snapshot(self):
        with self._lock:
            return {
                "writes_total": self.writes_total,
                "deletes_total": self.deletes_total,
                "reads_total": self.reads_total,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "replay_entries": self.replay_entries,
                "fsync_count": self.fsync_count,
                "fsync_ms_total": round(self.fsync_ms_total, 3),
                "corruption_events": self.corruption_events,
                "successful_replications": self.successful_replications,
                "failed_replications": self.failed_replications,
                "retry_count": self.retry_count,
                "degraded_replications": self.degraded_replications,
                "write_quorum_failures": self.write_quorum_failures,
                "read_quorum_failures": self.read_quorum_failures,
                "read_repairs": self.read_repairs,
                "hint_deliveries": self.hint_deliveries,
                "hint_failures": self.hint_failures,
                "quorum_latency_ms": (
                    round(
                        self.quorum_latency_ms_total / self.quorum_latency_count,
                        3,
                    )
                    if self.quorum_latency_count
                    else 0.0
                ),
                "replication_latency_ms": (
                    round(
                        self.replication_latency_ms_total
                        / self.replication_latency_count,
                        3,
                    )
                    if self.replication_latency_count
                    else 0.0
                ),
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


class FsyncTimer:
    def __init__(self, metrics):
        self.metrics = metrics
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self.metrics.record_fsync(elapsed_ms)
