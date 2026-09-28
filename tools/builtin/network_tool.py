"""Network diagnostic tools (Phase 15.1) — GREEN, informational only.

No shell, no subprocess, no external commands: everything uses the Python
standard library (socket) plus psutil, so the tools work on Windows and
Linux without privileges.

Reachability is measured with TCP handshakes (ports 80/443), NOT ICMP echo:
raw ICMP requires elevated privileges on most platforms, and parsing the
system `ping` binary is fragile across OSes. The `method` field always says
`tcp_connect` so callers know exactly what was measured.
"""

import ipaddress
import re
import socket
import time
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
import psutil

from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult

# DNS hostname label: 1-63 chars, alphanumerics and hyphens, no leading/trailing hyphen.
_HOSTNAME_REGEX = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.*$"
)

_PING_PORTS = (80, 443)
_PING_TIMEOUT_SECONDS = 2.0
_PING_MIN_COUNT = 1
_PING_MAX_COUNT = 10


def _validate_host(value: str, what: str = "hostname") -> str:
    """Accept an IP literal or a DNS hostname; reject shell/hostile input."""
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError(f"Invalid {what}: must be a non-empty hostname or IP.")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if not _HOSTNAME_REGEX.match(value):
        raise ValueError(f"Invalid {what}: {value!r}.")
    return value


def _resolve_addresses(hostname: str) -> List[str]:
    """Resolve all unique IP addresses for a hostname (raises socket.gaierror)."""
    infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    addresses: List[str] = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    return addresses


class PingHostArgs(BaseModel):
    hostname: str = Field(..., description="Hostname or IP address to probe")
    count: int = Field(default=4, description="Number of attempts (1-10)")


class PingHostTool(BaseTool):
    """Probe host reachability with TCP handshakes (no privileges needed)."""

    name: str = "ping_host"
    description: str = (
        "Check whether a host is reachable using TCP handshakes on ports 80/443 "
        "(no shell, no ICMP privileges required)."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = PingHostArgs
    # Hostname goes only to socket APIs (never a shell); validated in execute().
    param_kinds: Dict[str, ParamKind] = {"hostname": ParamKind.FREE_TEXT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        hostname = kwargs.get("hostname", "")
        count = kwargs.get("count", 4)
        try:
            count = int(count)
        except (TypeError, ValueError):
            return ToolResult.fail(
                error=f"Invalid count: {count!r}. Expected an integer 1-10.",
                security_level=self.security_level,
            )
        if not _PING_MIN_COUNT <= count <= _PING_MAX_COUNT:
            return ToolResult.fail(
                error=f"Invalid count: {count}. Expected 1-10.",
                security_level=self.security_level,
            )
        try:
            _validate_host(hostname)
        except ValueError as e:
            return ToolResult.fail(error=str(e), security_level=self.security_level)

        try:
            addresses = _resolve_addresses(hostname)
        except socket.gaierror as e:
            return ToolResult.ok(
                data={
                    "hostname": hostname,
                    "resolved_addresses": [],
                    "count": count,
                    "successful": 0,
                    "failed": count,
                    "packet_loss_percent": 100.0,
                    "latency_min_ms": None,
                    "latency_avg_ms": None,
                    "latency_max_ms": None,
                    "reachable": False,
                    "method": "tcp_connect",
                    "dns_error": str(e),
                },
                security_level=self.security_level,
            )

        latencies: List[float] = []
        refused = 0
        timeouts = 0
        for i in range(count):
            address = addresses[i % len(addresses)]
            port = _PING_PORTS[i % len(_PING_PORTS)]
            start = time.perf_counter()
            try:
                sock = socket.create_connection((address, port), timeout=_PING_TIMEOUT_SECONDS)
                sock.close()
                latencies.append((time.perf_counter() - start) * 1000.0)
            except socket.timeout:
                timeouts += 1
            except ConnectionRefusedError:
                refused += 1
            except OSError as e:
                if "timed out" in str(e).lower():
                    timeouts += 1
                else:
                    refused += 1

        successful = len(latencies)
        failed = count - successful
        return ToolResult.ok(
            data={
                "hostname": hostname,
                "resolved_addresses": addresses,
                "count": count,
                "successful": successful,
                "failed": failed,
                "refused_count": refused,
                "timeout_count": timeouts,
                "packet_loss_percent": round(100.0 * failed / count, 1),
                "latency_min_ms": round(min(latencies), 2) if latencies else None,
                "latency_avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "latency_max_ms": round(max(latencies), 2) if latencies else None,
                "reachable": successful > 0,
                "method": "tcp_connect",
            },
            security_level=self.security_level,
        )


class DnsLookupArgs(BaseModel):
    domain: str = Field(..., description="Domain name or IP to resolve")


class DnsLookupTool(BaseTool):
    """Resolve a domain to IP addresses using the standard library only."""

    name: str = "dns_lookup"
    description: str = "Resolve a domain name to IPv4/IPv6 addresses (no external commands)."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = DnsLookupArgs
    param_kinds: Dict[str, ParamKind] = {"domain": ParamKind.FREE_TEXT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        domain = kwargs.get("domain", "")
        try:
            _validate_host(domain, what="domain")
        except ValueError as e:
            return ToolResult.fail(error=str(e), security_level=self.security_level)
        try:
            try:
                infos = socket.getaddrinfo(domain, None, flags=socket.AI_CANONNAME)
            except (OSError, AttributeError):
                infos = socket.getaddrinfo(domain, None)
        except socket.gaierror as e:
            return ToolResult.ok(
                data={
                    "domain": domain,
                    "addresses": [],
                    "ipv4": [],
                    "ipv6": [],
                    "canonical_names": [],
                    "resolved": False,
                    "error": str(e),
                },
                security_level=self.security_level,
            )
        ipv4: List[str] = []
        ipv6: List[str] = []
        canonical: List[str] = []
        for info in infos:
            address = info[4][0]
            if ":" in address:
                if address not in ipv6:
                    ipv6.append(address)
            else:
                if address not in ipv4:
                    ipv4.append(address)
            canon = info[3]
            if canon and canon not in canonical:
                canonical.append(canon)
        return ToolResult.ok(
            data={
                "domain": domain,
                "addresses": ipv4 + ipv6,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "canonical_names": canonical,
                "resolved": True,
            },
            security_level=self.security_level,
        )


class GetNetworkInterfacesTool(BaseTool):
    """List network interfaces with addresses and stats (psutil, normalized)."""

    name: str = "get_network_interfaces"
    description: str = "List local network interfaces, addresses and link status."
    security_level: SecurityLevel = SecurityLevel.GREEN

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
        except Exception as e:
            return ToolResult.fail(
                error=f"Could not read network interfaces: {e}",
                security_level=self.security_level,
            )
        interfaces = []
        for name, addr_list in addrs.items():
            stat = stats.get(name)
            addresses = []
            for snic in addr_list:
                try:
                    family = socket.AddressFamily(int(snic.family)).name
                except (ValueError, AttributeError):
                    family = str(snic.family)
                addresses.append({
                    "family": family,
                    "address": snic.address,
                    "netmask": snic.netmask,
                    "broadcast": snic.broadcast,
                    "ptp": snic.ptp,
                })
            interfaces.append({
                "name": name,
                "is_up": bool(stat.isup) if stat else False,
                "speed_mbps": int(stat.speed) if stat else 0,
                "mtu": int(stat.mtu) if stat and stat.mtu else 0,
                "flags": stat.flags if stat and getattr(stat, "flags", None) else "",
                "addresses": addresses,
            })
        interfaces.sort(key=lambda i: i["name"])
        return ToolResult.ok(
            data={"interfaces": interfaces, "count": len(interfaces)},
            security_level=self.security_level,
        )
