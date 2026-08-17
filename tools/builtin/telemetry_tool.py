"""Real-time system telemetry collection tool."""

import platform
import time
from typing import Any, List, Optional
import psutil

from core.config import get_settings
from core.contracts.enums import SecurityLevel
from core.contracts.telemetry import (
    CPUMetrics,
    DiskMetrics,
    MemoryMetrics,
    ProcessInfo,
    SystemMetrics,
)
from core.contracts.tool import BaseTool, ToolResult


class GetSystemMetricsTool(BaseTool):
    """Tool that gathers truthful real-time hardware telemetry without estimation."""

    name: str = "get_system_metrics"
    description: str = "Query real-time hardware telemetry including CPU, RAM, and disk utilization."
    security_level: SecurityLevel = SecurityLevel.GREEN

    async def execute(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()
        start = time.perf_counter()

        # CPU Metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        per_core = psutil.cpu_percent(percpu=True)
        cpu_freq = psutil.cpu_freq()
        cpu_metrics = CPUMetrics(
            usage_percent=cpu_percent,
            cores_logical=psutil.cpu_count(logical=True) or 1,
            cores_physical=psutil.cpu_count(logical=False) or 1,
            frequency_mhz=cpu_freq.current if cpu_freq else None,
            per_core_percent=per_core,
        )

        # Memory Metrics
        vm = psutil.virtual_memory()
        mem_metrics = MemoryMetrics(
            total_bytes=vm.total,
            available_bytes=vm.available,
            used_bytes=vm.used,
            usage_percent=vm.percent,
        )

        # Disk Metrics
        disks: List[DiskMetrics] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(
                    DiskMetrics(
                        mount_point=part.mountpoint,
                        filesystem=part.fstype,
                        total_bytes=usage.total,
                        free_bytes=usage.free,
                        used_bytes=usage.used,
                        usage_percent=usage.percent,
                    )
                )
            except (PermissionError, OSError):
                continue

        # Top processes by memory
        top_procs: List[ProcessInfo] = []
        try:
            for p in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']),
                            key=lambda p: (p.info.get('memory_info').rss if p.info.get('memory_info') else 0),
                            reverse=True)[:5]:
                mem_rss = p.info.get('memory_info').rss if p.info.get('memory_info') else 0
                top_procs.append(
                    ProcessInfo(
                        pid=p.info['pid'],
                        name=p.info['name'] or "unknown",
                        cpu_percent=p.info.get('cpu_percent') or 0.0,
                        memory_bytes=mem_rss,
                        status=p.info.get('status') or "unknown",
                    )
                )
        except Exception:
            pass

        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time

        system_metrics = SystemMetrics(
            node_id=settings.node_id,
            os_name=platform.system(),
            os_version=platform.version(),
            uptime_seconds=uptime_seconds,
            cpu=cpu_metrics,
            memory=mem_metrics,
            disks=disks,
            top_processes=top_procs,
        )

        duration_ms = (time.perf_counter() - start) * 1000.0
        return ToolResult.ok(
            data=system_metrics.model_dump(),
            security_level=self.security_level,
            execution_time_ms=duration_ms,
        )
