"""Tests for the SERVER Gemini relay (/api/llm/*) and memory fallback.

The Gemini key lives only on the SERVER: the relay uses the SERVER-side
key, and tests assert it never appears in responses, logs or errors.
All upstream HTTP is mocked. No real network.
"""

import json

import httpx
import pytest

from core.config import get_settings, reset_settings


def _auth_headers():
    return {"Authorization": f"Bearer {get_settings().api_key}"}


class _FakeUpstreamResponse:
    def __init__(self, status_code=200, payload=None, chunks=None):
        self.status_code = status_code
        self._payload = payload
        self._chunks = chunks or []

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeUpstreamClient:
    """Records requests; behavior configured per test via class attrs."""
    last_request = None
    post_response = None
    get_response = None
    stream_response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).last_request = (url, dict(headers or {}), json)
        return self.post_response

    async def get(self, url, headers=None):
        type(self).last_request = (url, dict(headers or {}), None)
        return self.get_response

    def stream(self, method, url, headers=None, json=None):
        type(self).last_request = (url, dict(headers or {}), json)
        return self.stream_response


@pytest.fixture
def google_env(monkeypatch):
    import types as _types
    import httpx as _real_httpx

    monkeypatch.setenv("JARVIS_GOOGLE_API_KEY", "server-side-secret")
    monkeypatch.setenv("JARVIS_GOOGLE_BASE_URL", "https://fake-gemini.test/v1beta/openai/")
    monkeypatch.setenv("JARVIS_GOOGLE_MODEL", "gemini-3.7-flash")
    reset_settings()
    # Shim only the relay module's httpx reference: the tests' own
    # AsyncClient (imported from real httpx) must keep working.
    shim = _types.ModuleType("httpx_shim")
    shim.AsyncClient = _FakeUpstreamClient
    shim.TimeoutException = _real_httpx.TimeoutException
    shim.ConnectError = _real_httpx.ConnectError
    shim.NetworkError = _real_httpx.NetworkError
    monkeypatch.setattr("server.routers.llm.httpx", shim)
    _FakeUpstreamClient.last_request = None
    return _FakeUpstreamClient


@pytest.mark.asyncio
async def test_relay_chat_non_streaming_uses_server_key(google_env):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    google_env.post_response = _FakeUpstreamResponse(200, {"choices": [{"message": {"content": "hi"}}]})
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/llm/chat/completions",
                                     json={"model": "gemini-3.7-flash",
                                           "messages": [{"role": "user", "content": "hi"}]},
                                     headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hi"
    url, headers, _ = google_env.last_request
    assert url == "https://fake-gemini.test/v1beta/openai/chat/completions"
    assert headers["Authorization"] == "Bearer server-side-secret"


@pytest.mark.asyncio
async def test_relay_never_leaks_key_in_errors(google_env, caplog):
    import logging
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    google_env.post_response = _FakeUpstreamResponse(500, {"error": "overload"})
    app = create_app()
    transport = ASGITransport(app=app)
    with caplog.at_level(logging.WARNING):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/llm/chat/completions",
                                         json={"model": "m", "messages": []},
                                         headers=_auth_headers())
    assert response.status_code == 500
    assert "server-side-secret" not in response.text
    assert "server-side-secret" not in caplog.text


@pytest.mark.asyncio
async def test_relay_models_health_path(google_env):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    google_env.get_response = _FakeUpstreamResponse(200, {"data": [{"id": "gemini-3.7-flash"}]})
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/llm/models", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "gemini-3.7-flash"
    url, _, _ = google_env.last_request
    assert url == "https://fake-gemini.test/v1beta/openai/models"


@pytest.mark.asyncio
async def test_relay_streaming_preserves_bytes(google_env):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    frames = [b"data: {\"a\": 1}\n\n", b"data: [DONE]\n\n"]
    google_env.stream_response = _FakeUpstreamResponse(200, chunks=frames)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/llm/chat/completions",
                                 json={"model": "m", "messages": [], "stream": True},
                                 headers=_auth_headers()) as response:
            assert response.status_code == 200
            raw = await response.aread()
    assert raw == b"".join(frames)


@pytest.mark.asyncio
async def test_relay_503_without_server_key(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    monkeypatch.setenv("JARVIS_GOOGLE_API_KEY", "")
    reset_settings()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/llm/chat/completions", json={},
                                  headers=_auth_headers())).status_code == 503
        assert (await client.get("/api/llm/models", headers=_auth_headers())).status_code == 503


@pytest.mark.asyncio
async def test_relay_requires_auth():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/llm/chat/completions", json={})).status_code in (401, 403)
        assert (await client.get("/api/llm/models")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_core_google_slot_talks_to_server_relay(monkeypatch):
    """CORE cloud slot pointed at SERVER /api/llm answers end-to-end (mocked)."""
    from core.llm.external_provider import ExternalProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/llm/chat/completions"
        assert request.headers.get("authorization") == "Bearer node-shared-key"
        return httpx.Response(200, json={
            "model": "gemini-3.7-flash",
            "choices": [{"message": {"content": "via server"}, "finish_reason": "stop"}],
        })

    transport = httpx.MockTransport(handler)
    provider = ExternalProvider(
        base_url="http://fake-server:8000/api/llm",
        model="gemini-3.7-flash",
        api_key="node-shared-key",
        provider_name="google",
    )
    from unittest.mock import patch
    from core.contracts.llm import LLMMessage

    real_client_cls = httpx.AsyncClient

    class _RoutedClient:
        """httpx-compatible client routing every request through MockTransport."""

        def __init__(self, *args, **kwargs):
            self._kwargs = kwargs

        async def __aenter__(self):
            self._client = real_client_cls(transport=transport)
            return self

        async def __aexit__(self, *args):
            await self._client.aclose()
            return False

        async def post(self, url, headers=None, json=None):
            return await self._client.post(url, headers=headers, json=json)

    with patch("core.llm.external_provider.httpx.AsyncClient", _RoutedClient):
        response = await provider.generate(messages=[LLMMessage(role="user", content="hi")])
    assert response.error_msg is None
    assert response.content == "via server"


@pytest.mark.asyncio
async def test_memory_tool_falls_back_local_when_not_required(monkeypatch):
    from tools.builtin.memory_tool import SearchMemoryTool
    from tools.registry import ToolRegistry
    from core.network.central_state_client import CentralStateError

    async def _failing_search(query, limit=10):
        raise CentralStateError("down", kind="connection")

    class _FailingCentral:
        async def search_memory(self, query, limit=10):
            return await _failing_search(query, limit)

    import tools.builtin.memory_tool as memory_tool_mod
    monkeypatch.setattr(memory_tool_mod, "get_memory_provider", lambda: _FailingCentral())
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_REQUIRED", "false")
    reset_settings()

    registry = ToolRegistry()
    registry.register(SearchMemoryTool())
    result = await registry.execute_tool("search_memory", {"query": "anything"}, source="operator")
    # Explicit local fallback: succeeds (possibly empty), never a fake answer
    assert result.success is True


@pytest.mark.asyncio
async def test_memory_tool_fails_explicitly_when_required(monkeypatch):
    from tools.builtin.memory_tool import SearchMemoryTool
    from tools.registry import ToolRegistry
    from core.network.central_state_client import CentralStateError

    class _FailingCentral:
        async def search_memory(self, query, limit=10):
            raise CentralStateError("central memory down", kind="connection")

    import tools.builtin.memory_tool as memory_tool_mod
    monkeypatch.setattr(memory_tool_mod, "get_memory_provider", lambda: _FailingCentral())
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_REQUIRED", "true")
    reset_settings()

    registry = ToolRegistry()
    registry.register(SearchMemoryTool())
    result = await registry.execute_tool("search_memory", {"query": "anything"}, source="operator")
    assert result.success is False
    assert "central" in result.error.lower()
