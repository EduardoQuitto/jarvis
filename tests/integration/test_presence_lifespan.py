"""Lifespan integration: Core startup -> registration -> heartbeat task.

The SERVER is simulated with httpx.MockTransport (zero real network):
  POST /api/devices/          -> registration accepted
  POST /api/devices/heartbeat -> {"status": "ok"}

Flow under test:
  lifespan(app) startup -> NodePresenceManager.start() (non-blocking)
    -> register_device -> periodic heartbeat task running
  lifespan(app) shutdown -> task cancelled, no orphan, state cleared.
"""

import asyncio

import httpx
import pytest

from core.config import reset_settings
from core.network.node_client import RemoteNodeClient
from server.app import create_app, lifespan


class _CallLog:
    def __init__(self):
        self.registers = []
        self.heartbeats = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/devices/":
            self.registers.append(request)
            return httpx.Response(200, json={"device_id": "jarvis-core", "status": "ONLINE", "registered": True})
        if request.method == "POST" and request.url.path == "/api/devices/heartbeat":
            self.heartbeats.append(request)
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def simulated_transport(monkeypatch):
    """Route every RemoteNodeClient built by presence through MockTransport."""
    log = _CallLog()
    transport = httpx.MockTransport(log.handler)

    def _factory(base_url="", api_key="", timeout=30.0, **kwargs):
        return RemoteNodeClient(base_url=base_url, api_key=api_key, timeout=timeout, transport=transport)

    monkeypatch.setattr("core.network.node_presence.RemoteNodeClient", _factory)
    return log


@pytest.mark.asyncio
async def test_lifespan_registers_and_heartbeats_then_stops_cleanly(monkeypatch, simulated_transport):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_SERVER_HEARTBEAT_INTERVAL", "0.05")
    reset_settings()

    app = create_app()
    async with lifespan(app):
        presence = app.state.presence
        assert presence is not None
        assert presence.is_running is True
        await asyncio.sleep(0.25)
        assert len(simulated_transport.registers) >= 1
        assert len(simulated_transport.heartbeats) >= 1
        task = presence._task

    assert presence.is_running is False
    assert task.done()  # no orphan task
    assert getattr(app.state, "presence", None) is None


@pytest.mark.asyncio
async def test_lifespan_skips_presence_when_server_url_empty(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()

    app = create_app()
    async with lifespan(app):
        assert getattr(app.state, "presence", None) is None


@pytest.mark.asyncio
async def test_lifespan_shutdown_clean_with_server_offline(monkeypatch):
    def _offline_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(_offline_handler)

    def _factory(base_url="", api_key="", timeout=30.0, **kwargs):
        return RemoteNodeClient(base_url=base_url, api_key=api_key, timeout=timeout, transport=transport)

    monkeypatch.setattr("core.network.node_presence.RemoteNodeClient", _factory)
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    monkeypatch.setenv("JARVIS_SERVER_HEARTBEAT_INTERVAL", "0.05")
    reset_settings()

    app = create_app()
    async with lifespan(app):  # startup must not raise nor block
        assert app.state.presence.is_running is True
        await asyncio.sleep(0.1)
    assert app.state.presence is None  # shutdown cancelled everything cleanly
