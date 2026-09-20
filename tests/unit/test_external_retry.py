"""Tests for transient-error retry with backoff in ExternalProvider.generate().

Rules under test: retry only 408/429/500/502/503/504, max 3 total attempts,
waits ~1s then ~2s via asyncio.sleep (non-blocking), contract preserved
(LLMResponse with error_msg, never raises), and the API key never logged.
No real network is used.
"""

import json
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm.external_provider import ExternalProvider
from core.contracts.llm import LLMMessage


def _http_error(status_code):
    from httpx import HTTPStatusError, Request, Response
    mock_request = MagicMock(spec=Request)
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = status_code
    mock_response.text = json.dumps({"error": f"status {status_code}"})
    return HTTPStatusError(message=f"HTTP {status_code}", request=mock_request, response=mock_response)


def _ok_response(content="Recovered!"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "model": "m",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    resp.raise_for_status.return_value = None
    return resp


def _provider():
    return ExternalProvider(base_url="https://api.test.com/v1", model="m", api_key="k")


class _ClientContext:
    """Patch httpx.AsyncClient so .post follows the given side_effect list."""

    def __init__(self, side_effects):
        self.side_effects = side_effects
        self.mock_client = None
        self._patcher = None

    def __enter__(self):
        self.mock_client = AsyncMock()
        self.mock_client.post = AsyncMock(side_effect=self.side_effects)
        self._patcher = patch("core.llm.external_provider.httpx.AsyncClient")
        mock_client_cls = self._patcher.__enter__()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=self.mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        return self.mock_client

    def __exit__(self, *exc):
        return self._patcher.__exit__(*exc)


@pytest.mark.asyncio
async def test_503_then_success_on_second_attempt():
    p = _provider()
    with _ClientContext([_http_error(503), _ok_response()]) as mock_client:
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is None
    assert response.content == "Recovered!"
    assert mock_client.post.call_count == 2
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_503_twice_then_success_on_third_attempt():
    p = _provider()
    with _ClientContext([_http_error(503), _http_error(503), _ok_response()]) as mock_client:
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is None
    assert mock_client.post.call_count == 3
    assert [c.args[0] for c in mock_sleep.await_args_list] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_persistent_503_returns_final_error_after_3_attempts():
    p = _provider()
    with _ClientContext([_http_error(503)] * 3) as mock_client:
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()):
            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is not None
    assert "503" in response.error_msg
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_permanent_errors_never_retry(status):
    p = _provider()
    with _ClientContext([_http_error(status)]) as mock_client:
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is not None
    assert str(status) in response.error_msg
    assert mock_client.post.call_count == 1
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_transient_statuses_retry(status):
    p = _provider()
    with _ClientContext([_http_error(status), _ok_response()]) as mock_client:
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()):
            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is None
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_api_key_never_appears_in_logs(caplog):
    secret = "sk-test-secret-4f8a2c"
    p = ExternalProvider(base_url="https://api.test.com/v1", model="m", api_key=secret)
    with _ClientContext([_http_error(503), _http_error(500), _http_error(503)]):
        with patch("core.llm.external_provider.asyncio.sleep", new=AsyncMock()):
            with caplog.at_level(logging.WARNING, logger="jarvis.llm.external"):
                response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
    assert response.error_msg is not None
    assert secret not in caplog.text
