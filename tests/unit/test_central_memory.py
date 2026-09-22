"""Tests for central memory: provider + runtime backend selection.

No real network: MockTransport for the provider, stubs for the tool.
"""

import httpx
import pytest

from core.config import reset_settings
from core.network.central_state_client import CentralStateClient
from core.network.node_client import RemoteNodeClient
from memory import get_memory_provider
from memory.central_provider import CentralMemoryProvider
from memory.sqlite_provider import SQLiteMemoryProvider


def _central(handler):
    transport = httpx.MockTransport(handler)
    client = RemoteNodeClient(base_url="http://testserver", api_key="k", timeout=5.0, transport=transport)
    return CentralMemoryProvider(central=CentralStateClient(client=client))


@pytest.mark.asyncio
async def test_central_memory_set_get_search_delete():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/memory/set":
            return httpx.Response(200, json={"status": "stored", "key": "k1"})
        if request.method == "GET" and request.url.path == "/api/memory/get/k1":
            return httpx.Response(200, json={"key": "k1", "value": {"a": 1}, "category": "general"})
        if request.method == "POST" and request.url.path == "/api/memory/search":
            return httpx.Response(200, json={"results": [{"key": "k1", "value": {"a": 1},
                                                          "category": "general"}], "count": 1})
        if request.method == "DELETE" and request.url.path == "/api/memory/delete/k1":
            return httpx.Response(200, json={"status": "deleted", "key": "k1"})
        if request.method == "GET" and request.url.path == "/api/memory/get/missing":
            return httpx.Response(404, json={"detail": "Key not found"})
        return httpx.Response(404, json={"detail": "not found"})

    provider = _central(handler)
    await provider.set("k1", {"a": 1})
    entry = await provider.get("k1")
    assert entry.key == "k1"
    assert entry.value == {"a": 1}
    assert entry.category == "general"
    assert await provider.get("missing") is None
    results = await provider.search_memory("k", limit=5)
    assert results == [{"key": "k1", "value": {"a": 1}, "category": "general"}]
    assert await provider.delete("k1") is True


@pytest.mark.asyncio
async def test_central_memory_failure_is_explicit():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    from core.network.central_state_client import CentralStateError
    provider = _central(handler)
    with pytest.raises(CentralStateError):
        await provider.set("k", "v")


def test_get_memory_provider_defaults_local(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "false")
    reset_settings()
    assert isinstance(get_memory_provider(), SQLiteMemoryProvider)


def test_get_memory_provider_central_when_enabled(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "true")
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "k")
    reset_settings()
    assert isinstance(get_memory_provider(), CentralMemoryProvider)


@pytest.mark.asyncio
async def test_search_memory_tool_uses_runtime_backend(monkeypatch):
    from tools.builtin.memory_tool import SearchMemoryTool
    from tools.registry import ToolRegistry

    class _StubBackend:
        def __init__(self):
            self.calls = []

        async def search_memory(self, query, limit=10):
            self.calls.append((query, limit))
            return [{"key": "k", "value": "v", "category": "general"}]

    import tools.builtin.memory_tool as memory_tool_mod
    stub = _StubBackend()
    monkeypatch.setattr(memory_tool_mod, "get_memory_provider", lambda: stub)

    registry = ToolRegistry()
    registry.register(SearchMemoryTool())
    result = await registry.execute_tool("search_memory", {"query": "k"}, source="operator")
    assert result.success is True
    assert result.data["count"] == 1
    assert stub.calls == [("k", 10)]
