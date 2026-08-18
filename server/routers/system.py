"""Granular System telemetry routes for Windows Agent."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
import psutil

from core.contracts.telemetry import CPUMetrics, DiskMetrics, MemoryMetrics, ProcessInfo
from security.auth import require_node_auth

router = APIRouter(prefix="/system", tags=["System Hardware & Metrics"])


@router.get("/cpu", response_model=CPUMetrics)
async def get_cpu_metrics(_token: str = Depends(require_node_auth)):
    """Retrieve detailed CPU utilization and core metrics in real time."""
    cpu_percent = psutil.cpu_percent(interval=None)
    per_core = psutil.cpu_percent(percpu=True)
    cpu_freq = psutil.cpu_freq()
    return CPUMetrics(
        usage_percent=cpu_percent,
        cores_logical=psutil.cpu_count(logical=True) or 1,
        cores_physical=psutil.cpu_count(logical=False) or 1,
        frequency_mhz=cpu_freq.current if cpu_freq else None,
        per_core_percent=per_core,
    )


@router.get("/memory", response_model=MemoryMetrics)
async def get_memory_metrics(_token: str = Depends(require_node_auth)):
    """Retrieve detailed RAM memory telemetry in real time."""
    vm = psutil.virtual_memory()
    return MemoryMetrics(
        total_bytes=vm.total,
        available_bytes=vm.available,
        used_bytes=vm.used,
        usage_percent=vm.percent,
    )


@router.get("/disk", response_model=List[DiskMetrics])
async def get_disk_metrics(_token: str = Depends(require_node_auth)):
    """Retrieve disk partition and storage usage across all mounted volumes."""
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
    return disks


@router.get("/processes", response_model=Dict[str, Any])
async def get_system_processes(
    limit: int = Query(20, ge=1, le=100, description="Max number of processes to return"),
    sort_by: str = Query("memory", description="Sort by 'memory', 'cpu', or 'name'"),
    _token: str = Depends(require_node_auth),
):
    """Retrieve active system processes with resource consumption stats."""
    processes: List[ProcessInfo] = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            mem_rss = p.info.get('memory_info').rss if p.info.get('memory_info') else 0
            processes.append(
                ProcessInfo(
                    pid=p.info['pid'],
                    name=p.info['name'] or "unknown",
                    cpu_percent=p.info.get('cpu_percent') or 0.0,
                    memory_bytes=mem_rss,
                    status=p.info.get('status') or "running",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if sort_by == "cpu":
        processes.sort(key=lambda x: x.cpu_percent, reverse=True)
    elif sort_by == "name":
        processes.sort(key=lambda x: x.name.lower())
    else:
        processes.sort(key=lambda x: x.memory_bytes, reverse=True)

    return {
        "total_running": len(processes),
        "limit": limit,
        "processes": [p.model_dump() for p in processes[:limit]],
    }
