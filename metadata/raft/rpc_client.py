"""HTTP transport for Raft peer RPC."""

import logging
from typing import Dict, Optional, Set

import httpx

from metadata.raft.models import (
    AppendEntriesRequest,
    AppendEntriesResponse,
    RequestVoteRequest,
    RequestVoteResponse,
)

log = logging.getLogger(__name__)


class RaftRpcClient:
    """Sends RequestVote and AppendEntries RPCs to peer metadata nodes."""

    def __init__(self, peer_urls: Dict[str, str], timeout: float = 0.5) -> None:
        self._peer_urls = dict(peer_urls)
        self._timeout = timeout
        self._partitioned: Set[str] = set()

    def set_peer_urls(self, peer_urls: Dict[str, str]) -> None:
        self._peer_urls = dict(peer_urls)

    def partition(self, peer_ids: Set[str]) -> None:
        self._partitioned = set(peer_ids)

    def heal_partition(self) -> None:
        self._partitioned.clear()

    def _url(self, peer_id: str, path: str) -> str:
        base = self._peer_urls[peer_id].rstrip("/")
        return f"{base}{path}"

    def request_vote(self, peer_id: str, request: RequestVoteRequest) -> Optional[RequestVoteResponse]:
        if peer_id in self._partitioned:
            return None
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    self._url(peer_id, "/raft/request-vote"),
                    json=request.model_dump(),
                )
                if resp.status_code == 200:
                    return RequestVoteResponse(**resp.json())
        except Exception as exc:
            log.debug("request_vote failed", extra={"peer": peer_id, "error": str(exc)})
        return None

    def append_entries(self, peer_id: str, request: AppendEntriesRequest) -> Optional[AppendEntriesResponse]:
        if peer_id in self._partitioned:
            return None
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    self._url(peer_id, "/raft/append-entries"),
                    json=request.model_dump(),
                )
                if resp.status_code == 200:
                    return AppendEntriesResponse(**resp.json())
        except Exception as exc:
            log.debug("append_entries failed", extra={"peer": peer_id, "error": str(exc)})
        return None
