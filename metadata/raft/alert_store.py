"""In-memory alert store replicated via Raft."""

import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class AlertStore:
    """Thread-safe alert registry for the control plane."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._alerts: Dict[str, dict] = {}

    def add_alert(
        self,
        severity: str,
        node: str,
        description: str,
        alert_id: Optional[str] = None,
    ) -> dict:
        aid = alert_id or str(uuid.uuid4())
        record = {
            "id": aid,
            "severity": severity,
            "node": node,
            "description": description,
            "time": _now_ms(),
            "status": "active",
        }
        with self._lock:
            self._alerts[aid] = record
        log.info("alert added", extra={"alert_id": aid, "severity": severity})
        return dict(record)

    def remove_alert(self, alert_id: str) -> bool:
        with self._lock:
            if alert_id not in self._alerts:
                return False
            del self._alerts[alert_id]
            return True

    def list_alerts(self) -> List[dict]:
        with self._lock:
            return [dict(a) for a in self._alerts.values()]

    def load_snapshot(self, alerts: List[dict]) -> None:
        with self._lock:
            self._alerts = {a["id"]: dict(a) for a in alerts}

    def to_snapshot(self) -> List[dict]:
        with self._lock:
            return [dict(a) for a in self._alerts.values()]
