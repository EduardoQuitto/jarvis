"""Windows system telemetry and diagnostics collector."""

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional
import psutil

from core.contracts.telemetry import CPUMetrics, DiskMetrics, MemoryMetrics, ProcessInfo, SystemMetrics


class WindowsSystemCollector:
    """Collects real-time hardware telemetry and GPU info specific to Windows."""

    @staticmethod
    def is_windows() -> bool:
        return platform.system().lower() == "windows"

    @staticmethod
    def get_gpu_info() -> Optional[Dict[str, Any]]:
        """Query NVIDIA GPU metrics via nvidia-smi if available, without failing if absent."""
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return None

        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 7:
                    return {
                        "name": parts[0],
                        "driver_version": parts[1],
                        "memory_total_mb": float(parts[2]),
                        "memory_used_mb": float(parts[3]),
                        "memory_free_mb": float(parts[4]),
                        "utilization_percent": float(parts[5]),
                        "temperature_celsius": float(parts[6]),
                    }
        except Exception:
            pass

        return None

    @classmethod
    def collect(cls, node_id: str = "windows-agent") -> SystemMetrics:
        """Capture full truthful telemetry snapshot."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(percpu=True)
        cpu_freq = psutil.cpu_freq()
        cpu = CPUMetrics(
            usage_percent=cpu_percent,
            cores_logical=psutil.cpu_count(logical=True) or 1,
            cores_physical=psutil.cpu_count(logical=False) or 1,
            frequency_mhz=cpu_freq.current if cpu_freq else None,
            per_core_percent=per_core,
        )

        # RAM
        vm = psutil.virtual_memory()
        mem = MemoryMetrics(
            total_bytes=vm.total,
            available_bytes=vm.available,
            used_bytes=vm.used,
            usage_percent=vm.percent,
        )

        # Disks
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

        # Top processes
        top_procs: List[ProcessInfo] = []
        try:
            for p in sorted(
                psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']),
                key=lambda p: (p.info.get('memory_info').rss if p.info.get('memory_info') else 0),
                reverse=True
            )[:5]:
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

        return SystemMetrics(
            node_id=node_id,
            os_name=platform.system(),
            os_version=platform.version(),
            uptime_seconds=psutil.time.time() - psutil.boot_time(),
            cpu=cpu,
            memory=mem,
            disks=disks,
            top_processes=top_procs,
        )
