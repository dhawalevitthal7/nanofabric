"""Background worker that retries failed and pending replication jobs."""

import logging
import threading
from typing import Optional

from node.replication_service import ReplicationService

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 5.0


class ReplicationWorker:

    def __init__(
        self,
        replication_service: ReplicationService,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
    ):
        self._service = replication_service
        self._interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"replication-worker-{self._service.node_id}",
            daemon=True,
        )
        self._thread.start()
        recovered = self._service.recover_pending_jobs()
        log.info(
            "replication worker started",
            extra={
                "node_id": self._service.node_id,
                "recovered_jobs": recovered,
            },
        )

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def run_once(self) -> int:
        return self._service.retry_failed_replications()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                retried = self.run_once()
                if retried:
                    log.info(
                        "replication retry cycle complete",
                        extra={"retried": retried},
                    )
            except Exception as exc:
                log.warning(
                    "replication worker cycle failed",
                    extra={"error": str(exc)},
                )
            if self._stop_event.wait(self._interval_sec):
                break
