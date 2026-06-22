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
