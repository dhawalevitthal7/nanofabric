import threading
import time


class FlushWorker:
    """Background thread that batches oplog fsync calls."""

    def __init__(self, flush_callback, window_ms=10):
        self._flush_callback = flush_callback
        self._window_ms = window_ms
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="oplog-flush-worker",
            daemon=True,
        )
        self._thread.start()

    def notify(self):
        self._event.set()

    def flush_now(self):
        self._flush_callback()

    def stop(self):
        self._stop.set()
        self._event.set()
        self._thread.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            self._event.wait(timeout=self._window_ms / 1000.0)
            self._event.clear()
            if self._stop.is_set():
                break
            self._flush_callback()
