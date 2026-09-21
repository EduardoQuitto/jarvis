"""Unit tests for CentralStateClient (central conversations/memory/confirmations).

All HTTP is simulated via httpx.MockTransport — no real network.
"""

import httpx
import pytest

from core.config import reset_settings
from core.network.central_state_client import CentralStateClient, CentralStateError
from core.network.node_client import RemoteNodeClient, RemoteNodeError


def _make_central(handler):
    transport = httpx.MockTransport(handler)
    client = RemoteNodeClient(base_url="http://testserver", api_key="k", timeout=5.0, transport=transport)
    return CentralStateClient(client=client)


def test_from_settings_none_when_disabled(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "false")
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    assert CentralStateClient.from_settings() is None


def test_from_settings_none_without_server_url(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "true")
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    assert CentralStateClient.from_settings() is None


def test_from_settings_defaults_disabled():
    from core.config import Settings
    settings = Settings(_env_file=None)
    assert settings.central_state_enabled is False
    assert settings.central_state_required is False


@pytest.mark.asyncio
async def test_conversation_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer k"
        if request.method == "POST" and request.url.path == "/api/conversations/":
            return httpx.Response(200, json={"id": "sess-1", "created": True})
        if request.method == "POST" and request.url.path == "/api/conversations/sess-1/messages":
            return httpx.Response(200, json={"stored": True})
        if request.method == "GET" and request.url.path == "/api/conversations/sess-1/messages":
            return httpx.Response(200, json=[{"role": "user", "content": "hi"}])
        if request.method == "GET" and request.url.path == "/api/conversations/sess-1":
            return httpx.Response(200, json={"id": "sess-1", "title": "t"})
        if request.method == "GET" and request.url.path == "/api/conversations/":
            return httpx.Response(200, json=[{"id": "sess-1"}])
        return httpx.Response(404, json={"detail": "not found"})

    central = _make_central(handler)
    assert (await central.create_conversation("sess-1", title="t"))["created"] is True
    assert (await central.append_message("sess-1", "user", "hi"))["stored"] is True
    assert await central.get_messages("sess-1") == [{"role": "user", "content": "hi"}]
    assert (await central.get_conversation("sess-1"))["id"] == "sess-1"
    assert await central.list_conversations() == [{"id": "sess-1"}]
    assert await central.get_conversation("missing") is None


@pytest.mark.asyncio
async def test_memory_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/memory/set":
            return httpx.Response(200, json={"status": "stored", "key": "k1"})
        if request.method == "GET" and request.url.path == "/api/memory/get/k1":
            return httpx.Response(200, json={"key": "k1", "value": "v", "category": "general"})
        if request.method == "GET" and request.url.path == "/api/memory/get/missing":
            return httpx.Response(404, json={"detail": "Key not found"})
        if request.method == "POST" and request.url.path == "/api/memory/search":
            return httpx.Response(200, json={"results": [{"key": "k1"}], "count": 1})
        if request.method == "DELETE" and request.url.path == "/api/memory/delete/k1":
            return httpx.Response(200, json={"status": "deleted", "key": "k1"})
        return httpx.Response(404, json={"detail": "not found"})

    central = _make_central(handler)
    assert (await central.memory_set("k1", "v"))["status"] == "stored"
    assert (await central.memory_get("k1"))["value"] == "v"
    assert await central.memory_get("missing") is None
    assert await central.memory_search("k") == [{"key": "k1"}]
    assert await central.memory_delete("k1") is True


@pytest.mark.asyncio
async def test_confirmation_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/confirmations/":
            return httpx.Response(200, json={"confirmation_id": "cid-1", "created": True})
        if request.method == "POST" and request.url.path == "/api/confirmations/cid-1/resolve":
            return httpx.Response(200, json={"confirmation_id": "cid-1", "approved": True})
        if request.method == "GET" and request.url.path == "/api/confirmations/cid-1":
            return httpx.Response(200, json={"confirmation_id": "cid-1", "approved": True})
        if request.method == "POST" and request.url.path == "/api/confirmations/cid-1/consume":
            return httpx.Response(200, json={"confirmation_id": "cid-1", "approved": True})
        if request.method == "POST" and request.url.path == "/api/confirmations/cid-used/consume":
            return httpx.Response(409, json={"detail": "already consumed"})
        if request.method == "GET" and request.url.path == "/api/confirmations/pending":
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path == "/api/confirmations/cleanup":
            return httpx.Response(200, json={"removed": 2})
        return httpx.Response(404, json={"detail": "not found"})

    central = _make_central(handler)
    assert (await central.confirmation_create({"confirmation_id": "cid-1"}))["created"] is True
    assert (await central.confirmation_resolve("cid-1", approved=True))["approved"] is True
    assert (await central.confirmation_get("cid-1"))["approved"] is True
    assert (await central.confirmation_consume("cid-1", session_id="s"))["approved"] is True
    assert await central.confirmation_consume("cid-used", session_id="s") is None
    assert await central.confirmation_get("missing") is None
    assert await central.confirmations_pending() == []
    assert await central.confirmations_cleanup() == 2


@pytest.mark.asyncio
async def test_transport_errors_become_central_state_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    central = _make_central(handler)
    with pytest.raises(CentralStateError) as exc_info:
        await central.get_messages("sess-1")
    assert exc_info.value.kind == "connection"
    assert "get_messages" in exc_info.value.message


@pytest.mark.asyncio
async def test_server_errors_never_hidden():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    central = _make_central(handler)
    with pytest.raises(CentralStateError) as exc_info:
        await central.memory_get("k")
    assert exc_info.value.kind == "server_error"
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_invalid_payload_never_invented():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"Content-Type": "application/json"})

    central = _make_central(handler)
    with pytest.raises(CentralStateError) as exc_info:
        await central.list_conversations()
    assert exc_info.value.kind == "invalid_response"


def test_remote_error_wrapping_preserves_kind():
    err = CentralStateError.from_remote_error("op", RemoteNodeError("x", kind="timeout"))
    assert err.kind == "timeout"
    assert "op" in err.message
