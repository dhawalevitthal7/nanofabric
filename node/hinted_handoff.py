"""Hinted handoff — store writes for temporarily unavailable replicas."""

import json
import logging
from typing import Optional

from node.hint_store import Hint, HintStore
from node.metrics import Metrics
from node.replica_client import ReplicaClient, ReplicaClientError
from node.replication_models import ReplicateDeleteRequest, ReplicateRequest

log = logging.getLogger(__name__)


class HintedHandoff:

    def __init__(
        self,
        node_id: str,
        hint_store: HintStore,
        replica_client: ReplicaClient,
        metrics: Metrics,
        resolve_url_fn,
    ):
        self._node_id = node_id
        self._hint_store = hint_store
        self._replica_client = replica_client
        self._metrics = metrics
        self._resolve_url = resolve_url_fn

    def store_hint(
        self,
        target_node: str,
        block_id: str,
        version: int,
        data: str,
        lsn: int,
        is_delete: bool = False,
    ) -> Hint:
        payload = {
            "data": data,
            "lsn": lsn,
            "origin_node_id": self._node_id,
            "is_delete": is_delete,
        }
        hint = self._hint_store.create_hint(
            target_node=target_node,
            block_id=block_id,
            version=version,
            payload=payload,
        )
        log.info(
            "hint stored",
            extra={
                "target_node": target_node,
                "block_id": block_id,
                "version": version,
            },
        )
        return hint

    def deliver_hint(self, hint: Hint, addresses: dict) -> bool:
        payload = json.loads(hint.payload)
        try:
            target_url = self._resolve_url(hint.target_node, addresses)
            if payload.get("is_delete"):
                request = ReplicateDeleteRequest(
                    block_id=hint.block_id,
                    version=hint.version,
                    lsn=payload["lsn"],
                    origin_node_id=payload["origin_node_id"],
                )
                self._replica_client.replicate_delete(
                    target_url, hint.target_node, request
                )
            else:
                request = ReplicateRequest(
                    block_id=hint.block_id,
                    data=payload.get("data", ""),
                    version=hint.version,
                    lsn=payload["lsn"],
                    origin_node_id=payload["origin_node_id"],
                )
                self._replica_client.replicate_write(
                    target_url, hint.target_node, request
                )
            self._hint_store.mark_delivered(hint.hint_id)
            self._metrics.inc_hint_deliveries()
            log.info(
                "hint delivered",
                extra={"hint_id": hint.hint_id, "target_node": hint.target_node},
            )
            return True
        except ReplicaClientError as exc:
            self._metrics.inc_hint_failures()
            log.warning(
                "hint delivery failed",
                extra={"hint_id": hint.hint_id, "error": str(exc)},
            )
            return False

    def replay_pending(self, addresses: dict) -> int:
        delivered = 0
        for hint in self._hint_store.list_pending():
            if self.deliver_hint(hint, addresses):
                delivered += 1
        return delivered

    def list_hints(self):
        return self._hint_store.list_all()

    def list_pending(self):
        return self._hint_store.list_pending()
