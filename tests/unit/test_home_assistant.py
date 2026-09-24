"""Unit tests for the Home Assistant integration (Phase 15).

No real Home Assistant is required: all HTTP is simulated via
httpx.MockTransport, and no test touches the LAN.
"""

import json
import logging

import httpx
import pytest

from core.config import Settings, get_settings, reset_settings
from core.contracts.enums import SecurityLevel, ToolVisibility
from core.home_assistant.client import (
    HomeAssistantClient,
    HomeAssistantError,
    validate_ha_name,
)
from tools.registry import ToolRegistry


def _make_client(handler, base_url="http://ha.local:8123", token="test-token", timeout=5.0):
    transport = httpx.MockTransport(handler)
    return HomeAssistantClient(base_url=base_url, token=token, timeout=timeout, transport=transport)


def _enable_ha(monkeypatch, role="SERVER"):
    monkeypatch.setenv("JARVIS_NODE_ROLE", role)
    monkeypatch.setenv("JARVIS_HOME_ASSISTANT_ENABLED", "true")
    monkeypatch.setenv("JARVIS_HOME_ASSISTANT_URL", "http://ha.local:8123")
    monkeypatch.setenv("JARVIS_HOME_ASSISTANT_TOKEN", "test-token")
    reset_settings()


# --- configuration ---

def test_ha_defaults_disabled():
    settings = Settings(_env_file=None)
    assert settings.home_assistant_enabled is False
    assert settings.home_assistant_url == ""
    assert settings.home_assistant_token == ""
    assert settings.home_assistant_timeout == 10.0


def test_ha_config_from_env(monkeypatch):
    _enable_ha(monkeypatch)
    settings = get_settings()
    assert settings.home_assistant_enabled is True
    assert settings.home_assistant_url == "http://ha.local:8123"
    assert settings.home_assistant_token == "test-token"


# --- client: success paths ---

@pytest.mark.asyncio
async def test_health_and_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        assert request.url.path == "/api/"
        return httpx.Response(200, json={"message": "API running."})

    client = _make_client(handler)
    assert await client.health() == {"message": "API running."}
    assert seen["auth"] == "Bearer test-token"
    assert client.is_configured is True


@pytest.mark.asyncio
async def test_get_state_path_and_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states/light.sala"
        return httpx.Response(200, json={
            "entity_id": "light.sala", "state": "on",
            "attributes": {"brightness": 200},
            "last_changed": "2026-01-01T00:00:00", "last_updated": "2026-01-01T00:00:01",
        })

    client = _make_client(handler)
    state = await client.get_state("light.sala")
    assert state["state"] == "on"
    assert state["attributes"]["brightness"] == 200


@pytest.mark.asyncio
async def test_call_service_post_and_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/services/light/turn_on"
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=[{"entity_id": "light.sala"}])

    client = _make_client(handler)
    result = await client.call_service("light", "turn_on", {"entity_id": "light.sala"})
    assert result == [{"entity_id": "light.sala"}]
    assert seen["body"] == {"entity_id": "light.sala"}


# --- client: failure paths (standardized, token never leaks) ---

@pytest.mark.asyncio
async def test_auth_failure_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).health()
    assert exc_info.value.kind == "auth"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_not_found_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not found"})

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).get_state("light.nope")
    assert exc_info.value.kind == "not_found"


@pytest.mark.asyncio
async def test_rate_limited_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too many"})

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).get_states()
    assert exc_info.value.kind == "rate_limited"


@pytest.mark.asyncio
async def test_timeout_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).health()
    assert exc_info.value.kind == "timeout"


@pytest.mark.asyncio
async def test_server_error_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"message": "bad gateway"})

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).call_service("light", "turn_on", {})
    assert exc_info.value.kind == "server_error"
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_invalid_json_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json{{{", headers={"Content-Type": "application/json"})

    with pytest.raises(HomeAssistantError) as exc_info:
        await _make_client(handler).health()
    assert exc_info.value.kind == "invalid_response"


@pytest.mark.asyncio
async def test_unconfigured_client_errors():
    client = HomeAssistantClient(base_url="", token="")
    assert client.is_configured is False
    with pytest.raises(HomeAssistantError) as exc_info:
        await client.health()
    assert exc_info.value.kind == "configuration"

    with pytest.raises(HomeAssistantError):
        await HomeAssistantClient(base_url="http://x", token="").get_states()


@pytest.mark.asyncio
async def test_token_never_appears_in_errors_or_logs(caplog):
    secret = "ha-secret-TOKEN-xyz-123"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    client = _make_client(handler, token=secret)
    with caplog.at_level(logging.ERROR, logger="jarvis.home_assistant"):
        with pytest.raises(HomeAssistantError) as exc_info:
            await client.get_state("light.sala")
    assert secret not in str(exc_info.value)
    assert secret not in (exc_info.value.details or "")
    assert secret not in caplog.text


def test_validate_ha_name_accepts_real_formats():
    for valid in ["light.sala", "switch.quarto", "scene.cinema", "automation.acordar",
                  "script.turn_on", "sensor.temperatura_sala", "wake_on_lan",
                  "media_player.tv", "climate.ar", "cover.janela_1"]:
        assert validate_ha_name(valid) == valid


def test_validate_ha_name_rejects_shell_and_urls():
    for evil in ["light.sala; reboot", "x|y", "a&b", "http://evil.com/x", "../etc",
                 "", "UPPER", "with space", "semi;colon"]:
        with pytest.raises(HomeAssistantError):
            validate_ha_name(evil)


# --- tools: metadata, policy, execution ---

def _registered_ha_tools(monkeypatch):
    from tools import register_default_tools

    _enable_ha(monkeypatch)
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry


@pytest.mark.asyncio
async def test_tools_metadata_levels_and_visibility(monkeypatch):
    registry = _registered_ha_tools(monkeypatch)
    expected = {
        "home_assistant_get_state": SecurityLevel.GREEN,
        "home_assistant_get_states": SecurityLevel.GREEN,
        "home_assistant_call_service": SecurityLevel.YELLOW,
        "home_assistant_wake_on_lan": SecurityLevel.GREEN,
    }
    for name, level in expected.items():
        tool = registry.get(name)
        assert tool is not None, f"{name} not registered on SERVER+enabled"
        assert tool.security_level == level
        assert tool.visibility == ToolVisibility.SHARED


@pytest.mark.asyncio
async def test_get_state_tool_end_to_end(monkeypatch):
    import tools.builtin.home_assistant as ha_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "entity_id": "light.sala", "state": "off", "attributes": {},
            "last_changed": "t1", "last_updated": "t2",
        })

    monkeypatch.setattr(
        ha_module, "get_home_assistant_client",
        lambda: _make_client(handler),
    )
    registry = _registered_ha_tools(monkeypatch)
    result = await registry.execute_tool(
        "home_assistant_get_state", {"entity_id": "light.sala"}, source="operator",
    )
    assert result.success is True
    assert result.data["entity_id"] == "light.sala"
    assert result.data["state"] == "off"
    assert set(result.data) == {"entity_id", "state", "attributes", "last_changed", "last_updated"}


@pytest.mark.asyncio
async def test_get_states_tool_trims_response(monkeypatch):
    import tools.builtin.home_assistant as ha_module

    states = [{"entity_id": f"light.l{i}", "state": "on", "attributes": {"huge": "x" * 5000},
               "last_changed": "t", "last_updated": "t"} for i in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=states)

    monkeypatch.setattr(ha_module, "get_home_assistant_client", lambda: _make_client(handler))
    registry = _registered_ha_tools(monkeypatch)
    result = await registry.execute_tool(
        "home_assistant_get_states", {"limit": 2}, source="operator",
    )
    assert result.success is True
    assert result.data["returned"] == 2
    assert result.data["total"] == 5
    assert [e["entity_id"] for e in result.data["entities"]] == ["light.l0", "light.l1"]


@pytest.mark.asyncio
async def test_call_service_tool_posts_and_policy_blocks_unconfirmed(monkeypatch):
    import tools.builtin.home_assistant as ha_module

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=[])

    monkeypatch.setattr(ha_module, "get_home_assistant_client", lambda: _make_client(handler))
    registry = _registered_ha_tools(monkeypatch)

    # YELLOW without confirmation is blocked by the existing PolicyEngine
    denied = await registry.execute_tool(
        "home_assistant_call_service",
        {"domain": "scene", "service": "turn_on", "service_data": {"entity_id": "scene.cinema"}},
        confirmed=False, source="orchestrator",
    )
    assert denied.success is False
    assert "Policy Denied" in (denied.error or "")
    assert seen == {}  # HA never contacted

    allowed = await registry.execute_tool(
        "home_assistant_call_service",
        {"domain": "scene", "service": "turn_on", "service_data": {"entity_id": "scene.cinema"}},
        confirmed=True, source="operator",
    )
    assert allowed.success is True
    assert seen["path"] == "/api/services/scene/turn_on"
    assert seen["body"] == {"entity_id": "scene.cinema"}


@pytest.mark.asyncio
async def test_wake_on_lan_tool(monkeypatch):
    import tools.builtin.home_assistant as ha_module

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=[])

    monkeypatch.setattr(ha_module, "get_home_assistant_client", lambda: _make_client(handler))
    registry = _registered_ha_tools(monkeypatch)

    result = await registry.execute_tool(
        "home_assistant_wake_on_lan",
        {"mac": "AA:BB:CC:DD:EE:FF", "broadcast_address": "192.168.0.255", "broadcast_port": 9},
        source="operator",
    )
    assert result.success is True
    assert seen["path"] == "/api/services/wake_on_lan/send_magic_packet"
    assert seen["body"] == {"mac": "AA:BB:CC:DD:EE:FF",
                            "broadcast_address": "192.168.0.255", "broadcast_port": 9}

    bad_mac = await registry.execute_tool(
        "home_assistant_wake_on_lan", {"mac": "not-a-mac"}, source="operator",
    )
    assert bad_mac.success is False
    assert "Invalid MAC" in (bad_mac.error or "")


# --- registration gating: only SERVER+enabled executes HA ---

def test_ha_tools_not_registered_by_default(monkeypatch):
    from tools import register_default_tools

    monkeypatch.delenv("JARVIS_HOME_ASSISTANT_ENABLED", raising=False)
    reset_settings()
    registry = ToolRegistry()
    register_default_tools(registry)
    assert registry.get("home_assistant_get_state") is None
    assert registry.get("home_assistant_call_service") is None
    assert registry.get("echo") is not None  # everything else intact


def test_ha_tools_not_registered_on_core(monkeypatch):
    from tools import register_default_tools
    from tools.builtin.home_assistant import register_home_assistant_tools

    _enable_ha(monkeypatch, role="CORE")
    registry = ToolRegistry()
    assert register_home_assistant_tools(registry) is False
    register_default_tools(registry)
    assert registry.get("home_assistant_get_state") is None


def test_ha_tools_not_registered_when_disabled_on_server(monkeypatch):
    from tools.builtin.home_assistant import register_home_assistant_tools, is_home_assistant_available

    monkeypatch.setenv("JARVIS_NODE_ROLE", "SERVER")
    monkeypatch.setenv("JARVIS_HOME_ASSISTANT_ENABLED", "false")
    reset_settings()
    assert is_home_assistant_available() is False
    assert register_home_assistant_tools(ToolRegistry()) is False


def test_is_home_assistant_available_requires_all(monkeypatch):
    from tools.builtin.home_assistant import is_home_assistant_available

    _enable_ha(monkeypatch)
    assert is_home_assistant_available() is True

    monkeypatch.setenv("JARVIS_HOME_ASSISTANT_TOKEN", "")
    reset_settings()
    assert is_home_assistant_available() is False


# --- remote bridge: CORE discovers SHARED HA tools, SERVER executes ---

class _StubServerClient:
    """Minimal stand-in for RemoteNodeClient (no network)."""

    def __init__(self, tools, execute_result=None):
        self._tools = tools
        self._execute_result = execute_result
        self.execute_calls = []

    async def list_tools(self):
        return self._tools

    async def execute_shared_tool(self, tool_name, parameters):
        self.execute_calls.append((tool_name, parameters))
        return self._execute_result


@pytest.mark.asyncio
async def test_core_reaches_ha_through_remote_server_tool(monkeypatch):
    from tools.builtin.remote_tool import RemoteServerTool

    monkeypatch.setenv("JARVIS_SERVER_URL", "http://testserver")
    reset_settings()
    stub = _StubServerClient(
        tools=[{"name": "home_assistant_get_state", "visibility": "SHARED"}],
        execute_result={"success": True, "data": {"entity_id": "light.sala", "state": "on"},
                        "error": None, "execution_time_ms": 2.0, "security_level": "GREEN"},
    )
    tool = RemoteServerTool(client=stub)
    result = await tool.execute(tool_name="home_assistant_get_state",
                               parameters={"entity_id": "light.sala"})
    assert result.success is True
    assert result.data["state"] == "on"
    # Execution happened on the SERVER side of the stub, never locally
    assert stub.execute_calls == [("home_assistant_get_state", {"entity_id": "light.sala"})]
