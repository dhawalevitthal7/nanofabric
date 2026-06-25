"""HTTP client for probing node storage state during repair."""

import logging
from typing import Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


class NodeClientError(Exception):
    def __init__(self, node_id: str, message: str):
        self.node_id = node_id
        super().__init__(message)


class NodeClient:

    def __init__(self, timeout_sec: float = 5.0):
        self._timeout = timeout_sec

    def resolve_url(self, node_id: str, addresses: Dict[str, str]) -> str:
        address = addresses.get(node_id)
        if not address:
            raise NodeClientError(node_id, f"No address for node '{node_id}'")
        if address.startswith("http://") or address.startswith("https://"):
            return address.rstrip("/")
        return f"http://{address}"

    def list_blocks(self, node_id: str, addresses: Dict[str, str]) -> List[str]:
        url = f"{self.resolve_url(node_id, addresses)}/blocks"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json().get("blocks", [])
        except httpx.HTTPError as exc:
            raise NodeClientError(node_id, str(exc)) from exc

    def read_block(
        self,
        node_id: str,
        block_id: str,
        addresses: Dict[str, str],
    ) -> Optional[dict]:
        url = f"{self.resolve_url(node_id, addresses)}/read/{block_id}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise NodeClientError(node_id, str(exc)) from exc

    def get_merkle_root(
        self,
        node_id: str,
        addresses: Dict[str, str],
    ) -> dict:
        url = f"{self.resolve_url(node_id, addresses)}/merkle"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise NodeClientError(node_id, str(exc)) from exc

    def has_block(
        self,
        node_id: str,
        block_id: str,
        addresses: Dict[str, str],
    ) -> bool:
        record = self.read_block(node_id, block_id, addresses)
        return record is not None and not record.get("deleted", False)

    def replay_hints(self, node_id: str, addresses: Dict[str, str]) -> int:
        url = f"{self.resolve_url(node_id, addresses)}/hints/replay"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url)
                response.raise_for_status()
                return response.json().get("delivered", 0)
        except httpx.HTTPError as exc:
            raise NodeClientError(node_id, str(exc)) from exc
