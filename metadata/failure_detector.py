"""Background worker that marks nodes DOWN when heartbeats stop."""

import logging
import threading
from typing import Callable, Optional

from metadata.constants import FAILURE_CHECK_INTERVAL_SEC
from metadata.membership import MembershipRegistry

log = logging.getLogger(__name__)


class FailureDetector:
    """Periodically scans the registry and flags nodes that missed heartbeats."""

    def __init__(
        self,
        registry: MembershipRegistry,
        interval_sec: float = FAILURE_CHECK_INTERVAL_SEC,
        now_ms_fn: Optional[Callable[[], int]] = None,
    ):
        self._registry = registry
        self._interval_sec = interval_sec
        self._now_ms_fn = now_ms_fn
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="failure-detector",
            daemon=True,
        )
        self._thread.start()
        log.info("failure detector started", extra={"interval_sec": self._interval_sec})

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_sec):
            now_ms = self._now_ms_fn() if self._now_ms_fn else None
            self._registry.check_failures(now_ms=now_ms)
