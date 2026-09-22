"""Mocked integration: CLIENT -> SERVER gateway -> simulated CORE.

SERVER app runs in-process (role SERVER, isolated tmp DB) with a seeded
compute CORE. HTTP to the CORE is simulated (no real network, no LAN):

  CLIENT -> SERVER /api/chat/send|/stream -> fake CORE /internal/* -> response
"""

import json

import pytest

from core.config import get_settings, reset_settings
from core.contracts.device import DeviceCapability, DeviceRegistrationRequest, DeviceType
from core.device.registry import DeviceRegistry
from memory.sqlite_provider import SQLiteMemoryProvider


class _FakeCoreResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeCoreStream:
    def __init__(self, chunks, status_code=200):
        self.status_code = status_code
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeCoreHttp:
    """Simulated CORE: answers /internal/chat/send|/stream deterministically."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, headers=None, json=None):
        session_id = (json or {}).get("session_id") or "sess-core-1"
        frames = [
            f"event: start\ndata: {{\"session_id\": \"{session_id}\"}}\n\n".encode(),
            b"event: text_delta\ndata: {\"text\": \"core says hi\"}\n\n",
            f"event: done\ndata: {{\"session_id\": \"{session_id}\", \"response_text\": \"core says hi\"}}\n\n".encode(),
        ]
        assert url.endswith("/internal/chat/stream"), url
        return _FakeCoreStream(frames)

    async def post(self, url, headers=None, json=None):
        assert url.endswith("/internal/chat/send"), url
        payload = json or {}
        return _FakeCoreResponse(200, {
            "session_id": payload.get("session_id") or "sess-core-1",
            "response_text": f"core: {payload.get('message', '')}",
            "tool_calls": [],
            "needs_confirmation": False,
            "confirmation_id": None,
            "confirmation_details": None,
            "iterations_used": 1,
        })


def _seed_core(monkeypatch, tmp_path):
    import server.compute as compute_mod

    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw-int.db"))
    registry = DeviceRegistry(memory=mem)
    monkeypatch.setattr(compute_mod, "_registry", registry)
    return registry


@pytest.mark.asyncio
async def test_client_server_core_send_end_to_end(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.compute as compute_mod

    monkeypatch.setenv("JARVIS_NODE_ROLE", "SERVER")
    reset_settings()
    registry = _seed_core(monkeypatch, tmp_path)
    await registry.register_device(DeviceRegistrationRequest(
        device_id="jarvis-core", name="core", device_type=DeviceType.CORE,
        capabilities=[DeviceCapability.LLM], version="0.5.0",
        ip_address="10.0.0.8", port=8000,
    ))
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeCoreHttp)

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/send",
                                     json={"message": "hello", "session_id": "sess-e2e-1"},
                                     headers=headers)
    assert response.status_code == 200
    body = response.json()
    # Same functional contract as a local answer
    assert body["session_id"] == "sess-e2e-1"
    assert body["response_text"] == "core: hello"
    assert body["tool_calls"] == []
    assert body["needs_confirmation"] is False
    assert body["iterations_used"] == 1


@pytest.mark.asyncio
async def test_client_server_core_stream_end_to_end(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    monkeypatch.setenv("JARVIS_NODE_ROLE", "SERVER")
    reset_settings()
    import server.compute as compute_mod
    registry = _seed_core(monkeypatch, tmp_path)
    await registry.register_device(DeviceRegistrationRequest(
        device_id="jarvis-core", name="core", device_type=DeviceType.CORE,
        capabilities=[DeviceCapability.LLM], version="0.5.0",
        ip_address="10.0.0.8", port=8000,
    ))
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeCoreHttp)

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/chat/stream",
                                 json={"message": "hi", "session_id": "sess-e2e-2"},
                                 headers=headers) as response:
            assert response.status_code == 200
            raw = await response.aread()
    text = raw.decode()
    kinds = [line[len("event: "):] for line in text.split("\n")
             if line.startswith("event: ")]
    assert kinds == ["start", "text_delta", "done"]
    assert "core says hi" in text
    assert "sess-e2e-2" in text


@pytest.mark.asyncio
async def test_gateway_never_invents_answers_without_core(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.compute as compute_mod

    monkeypatch.setenv("JARVIS_NODE_ROLE", "SERVER")
    reset_settings()
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw-none.db"))
    monkeypatch.setattr(compute_mod, "_registry", DeviceRegistry(memory=mem))
    # Even with a hostile httpx mock, no CORE means no call happens
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeCoreHttp)

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/send",
                                     json={"message": "hello"}, headers=headers)
        assert response.status_code == 503
        assert "compute" in response.json()["detail"].lower()
