"""System diagnostics tools (Phase 15.1) — GREEN, truthful read-only data.

Values come from platform/psutil/settings only — never invented. No secrets:
only an explicit allowlist of non-sensitive fields is ever returned.
"""

import platform
import socket
import time
from datetime import datetime, timezone
from typing import Any
import psutil

from core.config import get_settings
from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from core.network.node_presence import project_version


class GetSystemInfoTool(BaseTool):
    """Report truthful host and JARVIS identity facts (no secrets)."""

    name: str = "get_system_info"
    description: str = "Report hostname, OS, CPU/RAM facts and JARVIS node identity."
    security_level: SecurityLevel = SecurityLevel.GREEN

    async def execute(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()
        return ToolResult.ok(
            data={
                "hostname": socket.gethostname(),
                "os": platform.system(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "cpu_logical": psutil.cpu_count(logical=True) or 0,
                "cpu_physical": psutil.cpu_count(logical=False) or 0,
                "total_ram_bytes": psutil.virtual_memory().total,
                "jarvis_version": project_version(),
                "node_id": settings.node_id,
                "node_role": settings.node_role.value,
            },
            security_level=self.security_level,
        )


class GetSystemUptimeTool(BaseTool):
    """Report boot time and uptime (psutil, no shell commands)."""

    name: str = "get_system_uptime"
    description: str = "Report system boot time and uptime."
    security_level: SecurityLevel = SecurityLevel.GREEN

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            boot_timestamp = float(psutil.boot_time())
        except Exception as e:
            return ToolResult.fail(
                error=f"Could not read boot time: {e}",
                security_level=self.security_level,
            )
        uptime_seconds = max(0.0, time.time() - boot_timestamp)
        remaining = int(uptime_seconds)
        days, remaining = divmod(remaining, 86400)
        hours, remaining = divmod(remaining, 3600)
        minutes, seconds = divmod(remaining, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        if minutes or hours or days:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return ToolResult.ok(
            data={
                "boot_time": datetime.fromtimestamp(boot_timestamp, tz=timezone.utc).isoformat(),
                "uptime_seconds": round(uptime_seconds, 1),
                "uptime_human": " ".join(parts),
            },
            security_level=self.security_level,
        )
