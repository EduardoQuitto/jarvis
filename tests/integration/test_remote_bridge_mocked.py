"""Mocked integration test: Core -> RemoteNodeClient -> simulated SERVER API.

Simulates the SERVER with httpx.MockTransport (no real network):
  GET  /tools         -> advertises echo (SHARED) + secret_local (LOCAL_ONLY)
  POST /tools/execute -> executes echo remotely, denies LOCAL_ONLY

Flow under test:
  ToolRegistry.execute_tool("remote_server_tool", ...)   [Core boundary]
    -> RemoteServerTool (checks SHARED via list_tools)
      -> RemoteNodeClient (HTTP transport only)
        -> simulated SERVER API
"""

import json

import httpx
import pytest

from core.config import reset_settings
from core.network.node_client import RemoteNodeClient
from tools.builtin.remote_tool import RemoteServerTool
from tools.registry import ToolRegistry


def _simulated_server_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/tools":
        return httpx.Response(200, json=[
            {"name": "echo", "description": "Echo", "security_level": "GREEN",
             "visibility": "SHARED", "parameters_schema": {}, "timeout_seconds": 30.0},
            {"name": "secret_local", "description": "Local only", "security_level": "GREEN",
             "visibility": "LOCAL_ONLY", "parameters_schema": {}, "timeout_seconds": 30.0},
        ])
    if request.method == "POST" and request.url.path == "/tools/execute":
        body = json.loads(request.content.decode() or "{}")
        assert body.get("confirmed") is False  # Core must never bypass SERVER policy
        if body.get("tool_name") == "echo":
            message = (body.get("parameters") or {}).get("message", "")
            return httpx.Response(200, json={
                "success": True, "data": {"echo": message}, "error": None,
                "execution_time_ms": 1.0, "security_level": "GREEN",
            })
        return httpx.Response(200, json={
            "success": False, "data": None, "error": "Policy Denied",
            "execution_time_ms": 1.0, "security_level": "GREEN",
        })
    return httpx.Response(404, json={"detail": "not found"})


@pytest.mark.asyncio
async def test_core_to_server_shared_echo_flow(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "test-key")
    reset_settings()

    transport = httpx.MockTransport(_simulated_server_handler)
    client = RemoteNodeClient(
        base_url="http://simulated-server:8000",
        api_key="test-key",
        timeout=5.0,
        transport=transport,
    )
    registry = ToolRegistry()
    registry.register(RemoteServerTool(client=client))

    result = await registry.execute_tool(
        "remote_server_tool",
        {"tool_name": "echo", "parameters": {"message": "hello from CORE"}},
        source="orchestrator",
    )
    assert result.success is True
    assert result.data == {"echo": "hello from CORE"}


@pytest.mark.asyncio
async def test_core_to_server_local_only_blocked_end_to_end(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    reset_settings()

    transport = httpx.MockTransport(_simulated_server_handler)
    client = RemoteNodeClient(
        base_url="http://simulated-server:8000",
        api_key="test-key",
        timeout=5.0,
        transport=transport,
    )
    registry = ToolRegistry()
    registry.register(RemoteServerTool(client=client))

    result = await registry.execute_tool(
        "remote_server_tool",
        {"tool_name": "secret_local", "parameters": {}},
        source="orchestrator",
    )
    assert result.success is False
    assert "LOCAL_ONLY" in (result.error or "")
