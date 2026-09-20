"""Unit tests for CORE auto-registration + heartbeat (NodePresenceManager).

No test here touches the real Ubuntu SERVER — HTTP is simulated via
httpx.MockTransport, and the manager is exercised with a stub client.
"""

import asyncio
import json
import time

import httpx
import pytest

from core.config import get_settings, reset_settings
from core.network.node_client import RemoteNodeClient, RemoteNodeError
from core.network.node_presence import NodePresenceManager, project_version


def _make_client(handler, base_url="http://testserver", api_key="test-key", timeout=5.0):
    transport = httpx.MockTransport(handler)
    return RemoteNodeClient(base_url=base_url, api_key=api_key, timeout=timeout, transport=transport)


class _StubClient:
    """Recording stub for RemoteNodeClient (no network)."""

    def __init__(self):
        self.register_calls = []
        self.heartbeat_calls = []
        self.register_results = []
        self.heartbeat_results = []

    @staticmethod
    def _next(queue, default):
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return default

    async def register_device(self, **kwargs):
        self.register_calls.append(kwargs)
        return self._next(self.register_results, {"device_id": kwargs.get("device_id"), "registered": True})

    async def heartbeat(self, **kwargs):
        self.heartbeat_calls.append(kwargs)
        return self._next(self.heartbeat_results, {"status": "ok"})


def _manager(stub=None, **overrides):
    params = {
        "client": stub or _StubClient(),
        "device_id": "jarvis-core",
        "interval": 30.0,
    }
    params.update(overrides)
    return NodePresenceManager(**params)


# --- configuration ---

def test_presence_config_defaults(monkeypatch):
    monkeypatch.delenv("JARVIS_SERVER_HEARTBEAT_INTERVAL", raising=False)
    monkeypatch.delenv("JARVIS_NODE_ADVERTISE_IP", raising=False)
    monkeypatch.delenv("JARVIS_NODE_ADVERTISE_PORT", raising=False)
    reset_settings()
    settings = get_settings()
    assert settings.server_heartbeat_interval == 30.0
    assert settings.node_advertise_ip == ""
    assert settings.node_advertise_port == 0


def test_presence_disabled_when_server_url_empty(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    assert NodePresenceManager.from_settings() is None


def test_presence_identity_and_version(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    monkeypatch.setenv("JARVIS_NODE_ID", "jarvis-core")
    reset_settings()
    manager = NodePresenceManager.from_settings(client=_StubClient())
    assert manager is not None
    assert manager._device_id == "jarvis-core"
    assert manager._device_type == "CORE"
    assert manager._capabilities == ["llm"]
    assert manager._name == "J.A.R.V.I.S. Core - i5-14400"
    assert manager._version == "0.5.0"
    assert project_version() == "0.5.0"


def test_presence_advertise_ip_port_optional(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    # Defaults: nothing announced (no inbound endpoint invented)
    manager = NodePresenceManager.from_settings(client=_StubClient())
    assert manager._ip_address is None
    assert manager._port is None

    monkeypatch.setenv("JARVIS_NODE_ADVERTISE_IP", "192.168.0.8")
    monkeypatch.setenv("JARVIS_NODE_ADVERTISE_PORT", "8000")
    reset_settings()
    manager = NodePresenceManager.from_settings(client=_StubClient())
    assert manager._ip_address == "192.168.0.8"
    assert manager._port == 8000


def test_presence_interval_from_env(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    monkeypatch.setenv("JARVIS_SERVER_HEARTBEAT_INTERVAL", "10.0")
    reset_settings()
    manager = NodePresenceManager.from_settings(client=_StubClient())
    assert manager._interval == 10.0


# --- RemoteNodeClient: register_device / heartbeat ---

@pytest.mark.asyncio
async def test_register_device_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/devices/"
        assert request.method == "POST"
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"device_id": "jarvis-core", "status": "ONLINE", "registered": True})

    client = _make_client(handler)
    result = await client.register_device(
        device_id="jarvis-core",
        name="J.A.R.V.I.S. Core - i5-14400",
        device_type="CORE",
        capabilities=["llm"],
        version="0.5.0",
    )
    assert result["registered"] is True
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["device_id"] == "jarvis-core"
    assert body["device_type"] == "CORE"
    assert body["capabilities"] == ["llm"]
    assert "ip_address" not in body  # not invented
    assert "port" not in body


@pytest.mark.asyncio
async def test_register_device_includes_ip_port_when_configured():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"device_id": "jarvis-core", "registered": True})

    client = _make_client(handler)
    await client.register_device(device_id="jarvis-core", ip_address="192.168.0.8", port=8000)
    assert seen["body"]["ip_address"] == "192.168.0.8"
    assert seen["body"]["port"] == 8000


@pytest.mark.asyncio
async def test_heartbeat_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/devices/heartbeat"
        assert request.method == "POST"
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "ok"})

    client = _make_client(handler)
    result = await client.heartbeat(device_id="jarvis-core", status="ONLINE", capabilities=["llm"])
    assert result == {"status": "ok"}
    assert seen["body"] == {"device_id": "jarvis-core", "status": "ONLINE", "capabilities": ["llm"]}


@pytest.mark.asyncio
async def test_register_auth_failure_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.register_device(device_id="jarvis-core")
    assert exc_info.value.kind == "auth"


@pytest.mark.asyncio
async def test_register_timeout_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.register_device(device_id="jarvis-core")
    assert exc_info.value.kind == "timeout"


@pytest.mark.asyncio
async def test_heartbeat_connection_error_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.heartbeat(device_id="jarvis-core")
    assert exc_info.value.kind == "connection"


@pytest.mark.asyncio
async def test_heartbeat_server_error_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.heartbeat(device_id="jarvis-core")
    assert exc_info.value.kind == "server_error"


@pytest.mark.asyncio
async def test_empty_device_id_rejected_locally():
    client = _make_client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.register_device(device_id="")
    assert exc_info.value.kind == "client_error"
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.heartbeat(device_id="")
    assert exc_info.value.kind == "client_error"


# --- NodePresenceManager behavior ---

@pytest.mark.asyncio
async def test_register_once_success():
    stub = _StubClient()
    manager = _manager(stub)
    assert await manager.register_once() is True
    assert manager.is_registered is True
    call = stub.register_calls[0]
    assert call["device_id"] == "jarvis-core"
    assert call["device_type"] == "CORE"
    assert call["capabilities"] == ["llm"]
    # Manager passes None through; RemoteNodeClient omits them from HTTP
    # (covered by test_register_device_posts_expected_payload).
    assert call["ip_address"] is None
    assert call["port"] is None


@pytest.mark.asyncio
async def test_server_offline_never_raises():
    stub = _StubClient()
    stub.register_results.append(RemoteNodeError("connection refused", kind="connection"))
    stub.heartbeat_results.append(RemoteNodeError("connection refused", kind="connection"))
    manager = _manager(stub)
    assert await manager.register_once() is False
    assert manager.is_registered is False
    assert await manager.heartbeat_once() is False


@pytest.mark.asyncio
async def test_retry_after_failure():
    stub = _StubClient()
    stub.register_results.append(RemoteNodeError("SERVER down", kind="connection"))
    manager = _manager(stub)
    assert await manager.register_once() is False
    assert await manager.register_once() is True  # next cycle recovers
    assert manager.is_registered is True
    assert len(stub.register_calls) == 2


@pytest.mark.asyncio
async def test_periodic_heartbeat_and_clean_stop():
    stub = _StubClient()
    manager = _manager(stub, interval=0.05)
    await manager.start()
    assert manager.is_running is True
    await asyncio.sleep(0.3)
    task = manager._task
    await manager.stop()
    assert manager.is_running is False
    assert task.done()  # no orphan task
    assert len(stub.register_calls) == 1
    assert len(stub.heartbeat_calls) >= 2  # periodic, not aggressive
    # Stopping twice is safe
    await manager.stop()


@pytest.mark.asyncio
async def test_start_does_not_block_on_offline_server():
    class _HangingClient(_StubClient):
        async def register_device(self, **kwargs):
            self.register_calls.append(kwargs)
            await asyncio.sleep(30)  # simulate unreachable SERVER hanging
            return {}

    manager = _manager(_HangingClient(), interval=0.05)
    started = time.perf_counter()
    await manager.start()  # must return immediately, never raise
    assert time.perf_counter() - started < 2.0
    await manager.stop()  # cancels the hanging attempt cleanly
    assert manager.is_running is False


@pytest.mark.asyncio
async def test_heartbeat_failure_triggers_reregister_next_cycle():
    stub = _StubClient()
    stub.heartbeat_results.append(RemoteNodeError("SERVER restarted", kind="connection"))
    manager = _manager(stub, interval=0.05)
    await manager.start()
    await asyncio.sleep(0.25)
    await manager.stop()
    assert len(stub.register_calls) >= 2  # re-registered after heartbeat failure
