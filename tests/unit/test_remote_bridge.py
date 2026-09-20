"""Unit tests for the CORE -> SERVER bridge (RemoteNodeClient + remote_server_tool).

No test here touches the real Ubuntu SERVER — all HTTP is simulated via
httpx.MockTransport.
"""

import json

import httpx
import pytest

from core.config import get_settings, reset_settings
from core.network.node_client import RemoteNodeClient, RemoteNodeError
from tools.builtin.remote_tool import RemoteServerTool, register_remote_tool
from tools.registry import ToolRegistry


def _make_client(handler, base_url="http://testserver", api_key="test-key", timeout=5.0):
    transport = httpx.MockTransport(handler)
    return RemoteNodeClient(base_url=base_url, api_key=api_key, timeout=timeout, transport=transport)


# --- configuration ---

def test_remote_bridge_config_defaults(monkeypatch):
    # _env_file=None ignores the developer's real .env, so this test
    # verifies the true code defaults (safe: bridge disabled).
    monkeypatch.delenv("JARVIS_SERVER_URL", raising=False)
    monkeypatch.delenv("JARVIS_SERVER_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_SERVER_TIMEOUT", raising=False)
    from core.config import Settings
    settings = Settings(_env_file=None)
    assert settings.server_url == ""
    assert settings.server_api_key == ""
    assert settings.server_timeout == 30.0


def test_remote_bridge_config_from_env(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://192.168.0.13:8000")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "secret-key")
    monkeypatch.setenv("JARVIS_SERVER_TIMEOUT", "12.5")
    reset_settings()
    settings = get_settings()
    assert settings.server_url == "http://192.168.0.13:8000"
    assert settings.server_api_key == "secret-key"
    assert settings.server_timeout == 12.5


# --- RemoteNodeClient: success paths ---

@pytest.mark.asyncio
async def test_health_success_and_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy", "node_id": "jarvis-server"})

    client = _make_client(handler)
    data = await client.health()
    assert data["status"] == "healthy"
    assert data["node_id"] == "jarvis-server"
    assert seen["auth"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_list_tools_success():
    payload = [
        {"name": "echo", "visibility": "SHARED", "security_level": "GREEN"},
        {"name": "secret_local", "visibility": "LOCAL_ONLY", "security_level": "GREEN"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tools"
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    tools = await client.list_tools()
    assert len(tools) == 2
    assert tools[0]["name"] == "echo"


@pytest.mark.asyncio
async def test_list_devices_success():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        assert request.url.path == "/api/devices/"
        return httpx.Response(200, json=[
            {"device_id": "dev-1", "status": "ONLINE"},
        ])

    client = _make_client(handler)
    devices = await client.list_devices()
    assert devices == [{"device_id": "dev-1", "status": "ONLINE"}]
    assert seen["auth"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_list_devices_unexpected_payload_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"device_id": "dev-1"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.list_devices()
    assert exc_info.value.kind == "invalid_response"


@pytest.mark.asyncio
async def test_execute_shared_tool_posts_confirmed_false():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tools/execute"
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"success": True, "data": {"echo": "hi"}, "error": None,
                  "execution_time_ms": 1.5, "security_level": "GREEN"},
        )

    client = _make_client(handler)
    result = await client.execute_shared_tool("echo", {"message": "hi"})
    assert result["success"] is True
    assert result["data"] == {"echo": "hi"}
    assert seen["body"]["tool_name"] == "echo"
    assert seen["body"]["parameters"] == {"message": "hi"}
    assert seen["body"]["confirmed"] is False


# --- RemoteNodeClient: failure paths (standardized RemoteNodeError) ---

@pytest.mark.asyncio
async def test_timeout_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.health()
    assert exc_info.value.kind == "timeout"


@pytest.mark.asyncio
async def test_connection_refused_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.health()
    assert exc_info.value.kind == "connection"


@pytest.mark.asyncio
async def test_auth_failure_401_and_403():
    for status in (401, 403):
        def handler(request: httpx.Request, _s=status) -> httpx.Response:
            return httpx.Response(_s, json={"detail": "unauthorized"})

        client = _make_client(handler)
        with pytest.raises(RemoteNodeError) as exc_info:
            await client.health()
        assert exc_info.value.kind == "auth"
        assert exc_info.value.status_code == status


@pytest.mark.asyncio
async def test_client_error_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.list_tools()
    assert exc_info.value.kind == "client_error"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_server_error_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.execute_shared_tool("echo", {})
    assert exc_info.value.kind == "server_error"
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_invalid_json_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"this is not json{{{", headers={"Content-Type": "application/json"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.health()
    assert exc_info.value.kind == "invalid_response"


@pytest.mark.asyncio
async def test_unconfigured_client_raises_configuration_error():
    client = RemoteNodeClient(base_url="", api_key="", timeout=5.0)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.health()
    assert exc_info.value.kind == "configuration"


# --- remote_server_tool: SHARED allow / LOCAL_ONLY block ---

class _StubClient:
    """Minimal stub standing in for RemoteNodeClient (no network)."""

    def __init__(self, tools, execute_result=None, execute_error=None):
        self._tools = tools
        self._execute_result = execute_result
        self._execute_error = execute_error
        self.execute_calls = []

    async def list_tools(self):
        if isinstance(self._tools, Exception):
            raise self._tools
        return self._tools

    async def execute_shared_tool(self, tool_name, parameters):
        self.execute_calls.append((tool_name, parameters))
        if self._execute_error is not None:
            raise self._execute_error
        return self._execute_result


@pytest.mark.asyncio
async def test_remote_tool_blocks_local_only(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubClient(tools=[{"name": "secret_local", "visibility": "LOCAL_ONLY"}])
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="secret_local", parameters={})
    assert result.success is False
    assert "LOCAL_ONLY" in (result.error or "")
    assert stub.execute_calls == []  # never forwarded to the SERVER


@pytest.mark.asyncio
async def test_remote_tool_rejects_unknown_tool(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubClient(tools=[{"name": "echo", "visibility": "SHARED"}])
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="nope", parameters={})
    assert result.success is False
    assert "not available as SHARED" in (result.error or "")
    assert stub.execute_calls == []


@pytest.mark.asyncio
async def test_remote_tool_executes_shared_tool(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubClient(
        tools=[{"name": "echo", "visibility": "SHARED"}],
        execute_result={"success": True, "data": {"echo": "hello"},
                        "error": None, "execution_time_ms": 2.0,
                        "security_level": "GREEN"},
    )
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="echo", parameters={"message": "hello"})
    assert result.success is True
    assert result.data == {"echo": "hello"}
    assert stub.execute_calls == [("echo", {"message": "hello"})]


@pytest.mark.asyncio
async def test_remote_tool_propagates_server_policy_denial(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubClient(
        tools=[{"name": "echo", "visibility": "SHARED"}],
        execute_result={"success": False, "data": None,
                        "error": "Policy Denied: needs confirmation",
                        "execution_time_ms": 1.0, "security_level": "YELLOW"},
    )
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="echo", parameters={})
    assert result.success is False
    assert "Policy Denied" in (result.error or "")
    assert str(result.security_level) == "SecurityLevel.YELLOW"


@pytest.mark.asyncio
async def test_remote_tool_network_error_returns_tool_result_not_exception(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubClient(
        tools=[{"name": "echo", "visibility": "SHARED"}],
        execute_error=RemoteNodeError("connection refused", kind="connection"),
    )
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="echo", parameters={})
    assert result.success is False
    assert "connection" in (result.error or "")


@pytest.mark.asyncio
async def test_remote_tool_without_server_url_fails_cleanly(monkeypatch):
    # Explicit empty string = disabled. (delenv alone is not enough: the
    # real .env may define JARVIS_SERVER_URL via dotenv.)
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    tool = RemoteServerTool(client=_StubClient(tools=[]))
    result = await tool.execute(tool_name="echo", parameters={})
    assert result.success is False
    assert "not configured" in (result.error or "")


# --- registry integration ---

def test_registry_skips_remote_tool_when_unconfigured(monkeypatch):
    # Explicit empty string = disabled. (delenv alone is not enough: the
    # real .env may define JARVIS_SERVER_URL via dotenv.)
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    registry = ToolRegistry()
    from tools import register_default_tools
    register_default_tools(registry)
    assert registry.get("remote_server_tool") is None
    assert registry.get("echo") is not None


def test_registry_includes_remote_tool_when_configured(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://192.168.0.13:8000")
    reset_settings()
    registry = ToolRegistry()
    from tools import register_default_tools
    register_default_tools(registry)
    assert registry.get("remote_server_tool") is not None


def test_register_remote_tool_helper(monkeypatch):
    # Explicit empty string = disabled. (delenv alone is not enough: the
    # real .env may define JARVIS_SERVER_URL via dotenv.)
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    registry = ToolRegistry()
    assert register_remote_tool(registry) is False
    assert registry.get("remote_server_tool") is None

    monkeypatch.setenv("JARVIS_SERVER_URL", "http://192.168.0.13:8000")
    reset_settings()
    assert register_remote_tool(registry) is True
    assert registry.get("remote_server_tool") is not None
