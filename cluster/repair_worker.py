"""Background daemon that runs cluster repair cycles every 30 seconds."""

import logging
import threading
from typing import Optional

from cluster.repair_service import RepairService

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 30.0


class RepairWorker:

    def __init__(
        self,
        repair_service: RepairService,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
    ):
        self._service = repair_service
        self._interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="repair-worker",
            daemon=True,
        )
        self._thread.start()
        recovered = self._service.recover_jobs()
        log.info("repair worker started", extra={"recovered_jobs": recovered})

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def run_once(self) -> dict:
        return self._service.run_repair_cycle()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self.run_once()
                if result.get("executed") or result.get("scheduled"):
                    log.info("repair cycle complete", extra=result)
            except Exception as exc:
                log.warning("repair worker cycle failed", extra={"error": str(exc)})
            if self._stop_event.wait(self._interval_sec):
                break
