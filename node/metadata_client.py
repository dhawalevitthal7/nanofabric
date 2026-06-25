"""HTTP client for fetching block placement and node addresses from metadata."""

import logging
from typing import Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


class MetadataClient:

    def __init__(self, metadata_url: str, timeout_sec: float = 5.0):
        self._metadata_url = metadata_url.rstrip("/")
        self._timeout = timeout_sec

    def get_block_locations(self, block_id: str) -> Optional[List[str]]:
        url = f"{self._metadata_url}/blocks/{block_id}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()["locations"]
        except httpx.HTTPError as exc:
            log.warning(
                "failed to fetch block locations",
                extra={"block_id": block_id, "error": str(exc)},
            )
            raise

    def get_node_addresses(self) -> Dict[str, str]:
        url = f"{self._metadata_url}/nodes"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                nodes = response.json()
                return {
                    node_id: record["address"]
                    for node_id, record in nodes.items()
                }
        except httpx.HTTPError as exc:
            log.warning("failed to fetch node addresses", extra={"error": str(exc)})
            raise

    def resolve_node_url(self, node_id: str, addresses: Dict[str, str]) -> str:
        address = addresses.get(node_id)
        if not address:
            raise KeyError(f"No address registered for node '{node_id}'")
        if address.startswith("http://") or address.startswith("https://"):
            return address.rstrip("/")
        return f"http://{address}"
