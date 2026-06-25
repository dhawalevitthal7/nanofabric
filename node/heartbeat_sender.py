"""Background heartbeat sender — registers and announces node liveness."""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from metadata.constants import HEARTBEAT_INTERVAL_SEC

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class HeartbeatSender:
    """Registers with metadata and sends periodic heartbeats."""

    def __init__(
        self,
        metadata_url: str,
        node_id: str,
        address: str,
        interval_sec: float = HEARTBEAT_INTERVAL_SEC,
        stats_provider=None,
    ):
        self._metadata_url = metadata_url.rstrip("/")
        self._node_id = node_id
        self._address = address
        self._interval_sec = interval_sec
        self._stats_provider = stats_provider
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"heartbeat-{self._node_id}",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "heartbeat sender started",
            extra={"node_id": self._node_id, "metadata_url": self._metadata_url},
        )

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _post(self, path: str, payload: dict) -> None:
        url = f"{self._metadata_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()

    def _register(self) -> None:
        self._post("/register", {"node_id": self._node_id, "address": self._address})

    def _send_heartbeat(self) -> None:
        payload = {"node_id": self._node_id, "timestamp": _now_ms()}
        if self._stats_provider is not None:
            try:
                stats = self._stats_provider()
                payload.update(
                    {
                        "block_count": stats.get("block_count", 0),
                        "used_bytes": stats.get("used_bytes", 0),
                        "last_lsn": stats.get("last_lsn", 0),
                    }
                )
            except Exception as exc:
                log.warning(
                    "failed to collect node stats for heartbeat",
                    extra={"node_id": self._node_id, "error": str(exc)},
                )
        self._post("/heartbeat", payload)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._register()
                self._send_heartbeat()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                log.warning(
                    "heartbeat failed, will retry",
                    extra={"node_id": self._node_id, "error": str(exc)},
                )
            if self._stop_event.wait(self._interval_sec):
                break
