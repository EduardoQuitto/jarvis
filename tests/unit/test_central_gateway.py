"""Tests for the SERVER gateway: discovery, internal endpoints, chat proxy.

SERVER role forwards /api/chat/send|/stream to an eligible CORE;
other roles answer locally. No real network: seeded registries and
mocked httpx. No LAN, no real CORE.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.config import get_settings, reset_settings
from core.contracts.device import (
    Device,
    DeviceCapability,
    DeviceRegistrationRequest,
    DeviceType,
    NodeStatus,
)
from core.device.registry import DeviceRegistry
from memory.sqlite_provider import SQLiteMemoryProvider


def _eligible_kwargs(**overrides):
    params = {
        "device_id": "jarvis-core",
        "name": "J.A.R.V.I.S. Core - i5-14400",
        "device_type": DeviceType.CORE,
        "capabilities": [DeviceCapability.LLM],
        "version": "0.5.0",
        "ip_address": "192.168.0.8",
        "port": 8000,
    }
    params.update(overrides)
    return params


def _seeded_registry(tmp_path, devices):
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw.db"))
    registry = DeviceRegistry(memory=mem)
    return mem, registry


@pytest.mark.asyncio
async def test_select_compute_node_prefers_eligible_core(tmp_path, monkeypatch):
    import server.compute as compute_mod

    mem, registry = _seeded_registry(tmp_path, None)
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs()))
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs(
        device_id="old-node", ip_address="192.168.0.9",
    )))
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs(
        device_id="mobile-1", device_type=DeviceType.MOBILE,
        capabilities=[DeviceCapability.SENSOR], ip_address="192.168.0.10",
    )))
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs(
        device_id="noaddr", ip_address="", port=0,
    )))
    monkeypatch.setattr(compute_mod, "_registry", registry)

    node = await compute_mod.select_compute_node()
    assert node is not None
    assert node.device_id in ("jarvis-core", "old-node")
    assert node.device_type == DeviceType.CORE
    assert node.ip_address and node.port


@pytest.mark.asyncio
async def test_select_compute_node_none_when_unavailable(tmp_path, monkeypatch):
    import server.compute as compute_mod

    mem, registry = _seeded_registry(tmp_path, None)
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs(
        device_id="stale", capabilities=[], ip_address="192.168.0.9",
    )))
    monkeypatch.setattr(compute_mod, "_registry", registry)
    assert await compute_mod.select_compute_node() is None

    mem2 = SQLiteMemoryProvider(db_path=str(tmp_path / "gw2.db"))
    monkeypatch.setattr(compute_mod, "_registry", DeviceRegistry(memory=mem2))
    assert await compute_mod.select_compute_node() is None


def test_is_compute_eligible_matrix():
    import server.compute as compute_mod
    from datetime import datetime, timezone

    def device(**overrides):
        params = {
            "device_id": "d", "name": "d", "device_type": DeviceType.CORE,
            "status": NodeStatus.ONLINE, "capabilities": [DeviceCapability.LLM],
            "version": "0.5.0", "ip_address": "192.168.0.8", "port": 8000,
            "last_seen": datetime.now(timezone.utc), "metadata": {},
        }
        params.update(overrides)
        return Device(**params)

    assert compute_mod.is_compute_eligible(device()) is True
    assert compute_mod.is_compute_eligible(device(status=NodeStatus.READY)) is True
    assert compute_mod.is_compute_eligible(device(status=NodeStatus.OFFLINE)) is False
    assert compute_mod.is_compute_eligible(device(device_type=DeviceType.MOBILE)) is False
    assert compute_mod.is_compute_eligible(device(capabilities=[])) is False
    assert compute_mod.is_compute_eligible(device(ip_address="")) is False
    assert compute_mod.is_compute_eligible(device(port=0)) is False
    assert compute_mod.compute_base_url(device()) == "http://192.168.0.8:8000"


class _FakeSyncResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, chunks, status_code=200):
        self.status_code = status_code
        self._chunks = chunks
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeHttpxClient:
    stream_response = None
    post_response = None
    posted = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        return self.stream_response

    async def post(self, url, headers=None, json=None):
        self.posted.append((url, json))
        return self.post_response


@pytest.mark.asyncio
async def test_forward_chat_send_success_and_contract(tmp_path, monkeypatch):
    import server.compute as compute_mod

    mem, registry = _seeded_registry(tmp_path, None)
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs()))
    monkeypatch.setattr(compute_mod, "_registry", registry)

    payload = {"session_id": "s", "response_text": "hi", "tool_calls": [],
               "needs_confirmation": False, "confirmation_id": None,
               "confirmation_details": None, "iterations_used": 1}
    _FakeHttpxClient.post_response = _FakeSyncResponse(200, payload)
    _FakeHttpxClient.posted = []
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeHttpxClient)

    result = await compute_mod.forward_chat_send({"message": "hi"})
    assert result["response_text"] == "hi"
    assert _FakeHttpxClient.posted[0][0] == "http://192.168.0.8:8000/internal/chat/send"


@pytest.mark.asyncio
async def test_forward_chat_send_no_core_is_explicit(tmp_path, monkeypatch):
    import server.compute as compute_mod
    from server.compute import ComputeUnavailable

    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw.db"))
    monkeypatch.setattr(compute_mod, "_registry", DeviceRegistry(memory=mem))
    with pytest.raises(ComputeUnavailable) as exc_info:
        await compute_mod.forward_chat_send({"message": "hi"})
    assert "No eligible compute CORE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_forward_chat_stream_relays_bytes_untouched(tmp_path, monkeypatch):
    import server.compute as compute_mod

    mem, registry = _seeded_registry(tmp_path, None)
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs()))
    monkeypatch.setattr(compute_mod, "_registry", registry)

    frames = [b"event: start\ndata: {\"a\": 1}\n\n", b"event: done\ndata: {}\n\n"]
    _FakeHttpxClient.stream_response = _FakeStreamResponse(frames)
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeHttpxClient)

    received = [chunk async for chunk in compute_mod.forward_chat_stream({"message": "hi"})]
    assert received == frames
    assert b"".join(received).endswith(b"\n\n")


@pytest.mark.asyncio
async def test_forward_chat_stream_disconnect_closes_upstream(tmp_path, monkeypatch):
    import server.compute as compute_mod

    mem, registry = _seeded_registry(tmp_path, None)
    await registry.register_device(DeviceRegistrationRequest(**_eligible_kwargs()))
    monkeypatch.setattr(compute_mod, "_registry", registry)

    stream = _FakeStreamResponse([b"event: start\ndata: {}\n\n", b"event: text_delta\ndata: {}\n\n"])
    _FakeHttpxClient.stream_response = stream
    monkeypatch.setattr(compute_mod.httpx, "AsyncClient", _FakeHttpxClient)

    agen = compute_mod.forward_chat_stream({"message": "hi"})
    first = await agen.__anext__()
    assert first.startswith(b"event: start")
    await agen.aclose()  # client disconnect
    assert stream.closed is True


def _server_role(monkeypatch):
    monkeypatch.setenv("JARVIS_NODE_ROLE", "SERVER")
    reset_settings()


@pytest.mark.asyncio
async def test_gateway_send_forwards_on_server_role(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.routers.chat as chat_module

    _server_role(monkeypatch)
    payload = {"session_id": "s", "response_text": "from core", "tool_calls": [],
               "needs_confirmation": False, "confirmation_id": None,
               "confirmation_details": None, "iterations_used": 1}
    with patch("server.routers.chat.forward_chat_send", new=AsyncMock(return_value=payload)) as mock_forward:
        app = create_app()
        headers = {"Authorization": f"Bearer {get_settings().api_key}"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat/send", json={"message": "hi"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["response_text"] == "from core"
    assert body["session_id"] == "s"
    mock_forward.assert_awaited_once()
    # Local orchestrator was never built for this request
    assert chat_module._orchestrator is None


@pytest.mark.asyncio
async def test_gateway_send_503_without_core(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.compute as compute_mod

    _server_role(monkeypatch)
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw-empty.db"))
    monkeypatch.setattr(compute_mod, "_registry", DeviceRegistry(memory=mem))
    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/send", json={"message": "hi"}, headers=headers)
    assert response.status_code == 503
    assert "compute" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_gateway_stream_proxies_sse_frames(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.compute as compute_mod

    _server_role(monkeypatch)
    # A compute node must exist: the handler pre-selects for an eager 503.
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw-seed.db"))
    seeded = DeviceRegistry(memory=mem)
    await seeded.register_device(DeviceRegistrationRequest(**_eligible_kwargs()))
    monkeypatch.setattr(compute_mod, "_registry", seeded)

    frames = [b"event: start\ndata: {\"session_id\": \"s\"}\n\n",
              b"event: text_delta\ndata: {\"text\": \"hi\"}\n\n",
              b"event: done\ndata: {}\n\n"]

    async def _fake_stream():
        for frame in frames:
            yield frame

    def _fake_factory(payload, node=None):
        assert node is not None and node.device_id == "jarvis-core"
        return _fake_stream()

    with patch("server.routers.chat.forward_chat_stream", side_effect=_fake_factory):
        app = create_app()
        headers = {"Authorization": f"Bearer {get_settings().api_key}"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("POST", "/api/chat/stream",
                                     json={"message": "hi"}, headers=headers) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                raw = await response.aread()
    assert raw == b"".join(frames)


@pytest.mark.asyncio
async def test_gateway_stream_503_without_core(tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    import server.compute as compute_mod

    _server_role(monkeypatch)
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "gw-empty2.db"))
    monkeypatch.setattr(compute_mod, "_registry", DeviceRegistry(memory=mem))
    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/chat/stream",
                                 json={"message": "hi"}, headers=headers) as response:
            assert response.status_code == 503


@pytest.mark.asyncio
async def test_internal_send_uses_local_orchestrator(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    from core.llm.mock_provider import MockLLMProvider
    from core.orchestrator.engine import Orchestrator
    import server.routers.chat as chat_module

    # NODE2 (conftest default): compute role allowed
    chat_module._orchestrator = Orchestrator(
        llm_provider=MockLLMProvider(default_text="core answer"))
    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/internal/chat/send",
                                     json={"message": "hi"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["response_text"] == "core answer"


@pytest.mark.asyncio
async def test_internal_stream_serves_sse(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    from core.llm.mock_provider import MockLLMProvider
    from core.orchestrator.engine import Orchestrator
    import server.routers.chat as chat_module

    chat_module._orchestrator = Orchestrator(
        llm_provider=MockLLMProvider(default_text="core stream"))
    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/internal/chat/stream",
                                 json={"message": "hi"}, headers=headers) as response:
            assert response.status_code == 200
            raw = await response.aread()
    text = raw.decode()
    assert "event: start" in text
    assert text.rstrip().endswith("}")
    assert "event: done" in text


@pytest.mark.asyncio
async def test_internal_refused_on_server_role(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    _server_role(monkeypatch)
    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/internal/chat/send",
                                  json={"message": "hi"}, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_internal_requires_auth():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/internal/chat/send",
                                  json={"message": "hi"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_devices_list_exposes_compute_fields():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/devices/", json={
            "device_id": "jarvis-core", "name": "core", "device_type": "CORE",
            "capabilities": ["llm"], "version": "0.5.0",
            "ip_address": "192.168.0.8", "port": 8000,
        }, headers=headers)
        devices = (await client.get("/api/devices/", headers=headers)).json()
    core = next(d for d in devices if d["device_id"] == "jarvis-core")
    assert core["ip_address"] == "192.168.0.8"
    assert core["port"] == 8000
    assert "llm" in core["capabilities"]
    assert core["status"] == "ONLINE"
