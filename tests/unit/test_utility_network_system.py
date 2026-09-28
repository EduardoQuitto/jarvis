"""Unit tests for network + system diagnostic tools (Phase 15.1).

No real network is required beyond loopback: localhost resolves locally,
127.0.0.1 assertions are structural (no reachability assumed), and DNS
failure uses the reserved .invalid TLD.
"""

import pytest

from tools.registry import ToolRegistry
from tools.builtin.network_tool import (
    PingHostTool,
    DnsLookupTool,
    GetNetworkInterfacesTool,
)
from tools.builtin.system_info_tool import GetSystemInfoTool, GetSystemUptimeTool


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


# --- ping_host ---

@pytest.mark.asyncio
async def test_ping_localhost_structure():
    registry = _registry(PingHostTool())
    result = await registry.execute_tool(
        "ping_host", {"hostname": "127.0.0.1", "count": 2}, source="orchestrator",
    )
    assert result.success is True
    data = result.data
    assert data["hostname"] == "127.0.0.1"
    assert data["resolved_addresses"] == ["127.0.0.1"]
    assert data["count"] == 2
    assert data["successful"] + data["failed"] == 2
    assert data["packet_loss_percent"] == round(100.0 * data["failed"] / 2, 1)
    assert data["reachable"] == (data["successful"] > 0)
    assert data["method"] == "tcp_connect"
    if data["successful"]:
        assert data["latency_min_ms"] <= data["latency_avg_ms"] <= data["latency_max_ms"]
    else:
        assert data["latency_avg_ms"] is None


@pytest.mark.asyncio
async def test_ping_dns_failure_is_structured_not_crash():
    registry = _registry(PingHostTool())
    result = await registry.execute_tool(
        "ping_host", {"hostname": "nonexistent.invalid", "count": 2}, source="orchestrator",
    )
    assert result.success is True
    assert result.data["resolved_addresses"] == []
    assert result.data["reachable"] is False
    assert result.data["failed"] == 2
    assert "dns_error" in result.data


@pytest.mark.asyncio
async def test_ping_invalid_inputs():
    registry = _registry(PingHostTool())
    bad_host = await registry.execute_tool(
        "ping_host", {"hostname": "a; reboot", "count": 2}, source="orchestrator",
    )
    assert bad_host.success is False
    for bad_count in (0, 11, -1):
        bad = await registry.execute_tool(
            "ping_host", {"hostname": "127.0.0.1", "count": bad_count}, source="orchestrator",
        )
        assert bad.success is False


# --- dns_lookup ---

@pytest.mark.asyncio
async def test_dns_localhost():
    registry = _registry(DnsLookupTool())
    result = await registry.execute_tool(
        "dns_lookup", {"domain": "localhost"}, source="orchestrator",
    )
    assert result.success is True
    assert "127.0.0.1" in result.data["ipv4"]
    assert result.data["resolved"] is True
    assert isinstance(result.data["ipv6"], list)
    assert isinstance(result.data["canonical_names"], list)


@pytest.mark.asyncio
async def test_dns_invalid_domain():
    registry = _registry(DnsLookupTool())
    result = await registry.execute_tool(
        "dns_lookup", {"domain": "nonexistent.invalid"}, source="orchestrator",
    )
    assert result.success is True
    assert result.data["resolved"] is False
    assert result.data["addresses"] == []


@pytest.mark.asyncio
async def test_dns_rejects_hostile_input():
    registry = _registry(DnsLookupTool())
    result = await registry.execute_tool(
        "dns_lookup", {"domain": "x; rm -rf /"}, source="orchestrator",
    )
    assert result.success is False


# --- get_network_interfaces ---

@pytest.mark.asyncio
async def test_network_interfaces_schema():
    registry = _registry(GetNetworkInterfacesTool())
    result = await registry.execute_tool("get_network_interfaces", {}, source="orchestrator")
    assert result.success is True
    interfaces = result.data["interfaces"]
    assert len(interfaces) >= 1
    assert result.data["count"] == len(interfaces)
    required_iface = {"name", "is_up", "speed_mbps", "mtu", "flags", "addresses"}
    required_addr = {"family", "address", "netmask", "broadcast", "ptp"}
    assert any(iface["is_up"] for iface in interfaces)
    for iface in interfaces:
        assert required_iface <= set(iface)
        for addr in iface["addresses"]:
            assert required_addr <= set(addr)
    assert any(
        addr["address"] == "127.0.0.1"
        for iface in interfaces for addr in iface["addresses"]
    )


# --- get_system_info / get_system_uptime ---

@pytest.mark.asyncio
async def test_system_info_real_values_and_no_secrets():
    import json

    registry = _registry(GetSystemInfoTool())
    result = await registry.execute_tool("get_system_info", {}, source="orchestrator")
    assert result.success is True
    data = result.data
    assert data["hostname"]
    assert data["os"]
    assert data["cpu_logical"] >= 1
    assert data["total_ram_bytes"] > 0
    assert data["python_version"]
    assert data["node_id"]
    assert data["node_role"]
    assert data["jarvis_version"]
    blob = json.dumps(data)
    assert "api_key" not in blob
    assert "token" not in blob
    from core.config import get_settings
    assert get_settings().api_key not in blob


@pytest.mark.asyncio
async def test_system_uptime_schema_and_values():
    import re

    registry = _registry(GetSystemUptimeTool())
    result = await registry.execute_tool("get_system_uptime", {}, source="orchestrator")
    assert result.success is True
    data = result.data
    assert data["uptime_seconds"] > 0
    assert data["boot_time"]
    assert re.fullmatch(r"(\d+d )?(\d+h )?(\d+m )?\d+s", data["uptime_human"])
