"""HTTP client for sending replication requests to replica nodes."""

import logging
from typing import Optional

import httpx

from node.replication_models import ReplicateDeleteRequest, ReplicateRequest, ReplicateResponse

log = logging.getLogger(__name__)


class ReplicaClientError(Exception):
    def __init__(self, target_node: str, message: str, status_code: Optional[int] = None):
        self.target_node = target_node
        self.status_code = status_code
        super().__init__(message)


class ReplicaClient:

    def __init__(
        self,
        timeout_sec: float = 5.0,
        max_retries: int = 2,
        retry_delay_sec: float = 0.1,
    ):
        self._timeout = timeout_sec
        self._max_retries = max_retries
        self._retry_delay_sec = retry_delay_sec

    def replicate_write(
        self,
        target_url: str,
        target_node: str,
        request: ReplicateRequest,
    ) -> ReplicateResponse:
        return self._post_replicate(
            target_url,
            target_node,
            "/replicate",
            request.model_dump(),
        )

    def replicate_delete(
        self,
        target_url: str,
        target_node: str,
        request: ReplicateDeleteRequest,
    ) -> ReplicateResponse:
        return self._post_replicate(
            target_url,
            target_node,
            "/replicate-delete",
            request.model_dump(),
        )

    def read_block(
        self,
        target_url: str,
        target_node: str,
        block_id: str,
    ) -> Optional[dict]:
        url = f"{target_url.rstrip('/')}/read/{block_id}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                if response.status_code == 404:
                    return None
                if response.status_code >= 400:
                    raise ReplicaClientError(
                        target_node,
                        f"HTTP {response.status_code}: {response.text}",
                        status_code=response.status_code,
                    )
                return response.json()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            raise ReplicaClientError(
                target_node,
                f"replica unreachable: {exc}",
            ) from exc

    def _post_replicate(
        self,
        target_url: str,
        target_node: str,
        path: str,
        payload: dict,
    ) -> ReplicateResponse:
        url = f"{target_url.rstrip('/')}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, json=payload)
                    if response.status_code == 409:
                        raise ReplicaClientError(
                            target_node,
                            response.text,
                            status_code=409,
                        )
                    if response.status_code >= 400:
                        raise ReplicaClientError(
                            target_node,
                            f"HTTP {response.status_code}: {response.text}",
                            status_code=response.status_code,
                        )
                    data = response.json()
                    return ReplicateResponse(**data)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = exc
                log.warning(
                    "replica request failed, will retry",
                    extra={
                        "target_node": target_node,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                if attempt < self._max_retries:
                    import time
                    time.sleep(self._retry_delay_sec)

        raise ReplicaClientError(
            target_node,
            f"replica unreachable after {self._max_retries + 1} attempts: {last_error}",
        )
