"""Background worker that retries hinted handoff delivery."""

import logging
import threading
import time
from typing import Callable, Optional

from node.hinted_handoff import HintedHandoff

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 5.0


class HintWorker:

    def __init__(
        self,
        hinted_handoff: HintedHandoff,
        addresses_provider: Callable[[], dict],
        interval_sec: float = DEFAULT_INTERVAL_SEC,
    ):
        self._handoff = hinted_handoff
        self._addresses_provider = addresses_provider
        self._interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="hint-worker",
            daemon=True,
        )
        self._thread.start()
        log.info("hint worker started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval_sec + 2)
            self._thread = None
        log.info("hint worker stopped")

    def run_once(self) -> int:
        addresses = self._addresses_provider()
        delivered = self._handoff.replay_pending(addresses)
        cleaned = self._handoff._hint_store.delete_delivered()
        if delivered or cleaned:
            log.info(
                "hint worker cycle",
                extra={"delivered": delivered, "cleaned": cleaned},
            )
        return delivered

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("hint worker error")
            self._stop_event.wait(self._interval_sec)
