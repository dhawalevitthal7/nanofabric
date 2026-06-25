"""Tests for ReplicaClient HTTP communication."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from node.replica_client import ReplicaClient, ReplicaClientError
from node.replication_models import ReplicateRequest


def test_replicate_write_success():
    client = ReplicaClient(max_retries=0)
    request = ReplicateRequest(
        block_id="invoice-1",
        data="hello",
        version=1,
        lsn=10,
        origin_node_id="node1",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "node_id": "node2",
        "version": 1,
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.post.return_value = mock_response
        mock_client_cls.return_value = mock_http

        result = client.replicate_write("http://node2:8002", "node2", request)
        assert result.status == "success"
        assert result.node_id == "node2"


def test_replicate_write_timeout_retries():
    client = ReplicaClient(max_retries=1, retry_delay_sec=0)
    request = ReplicateRequest(
        block_id="invoice-1",
        data="hello",
        version=1,
        lsn=10,
        origin_node_id="node1",
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.post.side_effect = httpx.TimeoutException("timeout")
        mock_client_cls.return_value = mock_http

        with pytest.raises(ReplicaClientError):
            client.replicate_write("http://node2:8002", "node2", request)


def test_replicate_write_version_conflict():
    client = ReplicaClient(max_retries=0)
    request = ReplicateRequest(
        block_id="invoice-1",
        data="hello",
        version=1,
        lsn=10,
        origin_node_id="node1",
    )

    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_response.text = "version conflict"

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.post.return_value = mock_response
        mock_client_cls.return_value = mock_http

        with pytest.raises(ReplicaClientError) as exc_info:
            client.replicate_write("http://node2:8002", "node2", request)
        assert exc_info.value.status_code == 409
