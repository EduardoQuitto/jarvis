"""Telemetry and system state data transfer objects."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class CPUMetrics(BaseModel):
    """CPU metrics structure."""
    usage_percent: float = Field(..., description="Overall CPU usage percentage")
    cores_logical: int = Field(..., description="Number of logical cores")
    cores_physical: Optional[int] = Field(None, description="Number of physical cores")
    frequency_mhz: Optional[float] = Field(None, description="Current CPU frequency in MHz")
    per_core_percent: List[float] = Field(default_factory=list, description="Usage percentage per logical core")


class MemoryMetrics(BaseModel):
    """RAM metrics structure."""
    total_bytes: int = Field(..., description="Total system RAM in bytes")
    available_bytes: int = Field(..., description="Available RAM in bytes")
    used_bytes: int = Field(..., description="Used RAM in bytes")
    usage_percent: float = Field(..., description="RAM usage percentage")


class DiskMetrics(BaseModel):
    """Disk partition metrics structure."""
    mount_point: str = Field(..., description="Drive letter or mount path")
    filesystem: Optional[str] = Field(None, description="Filesystem type (NTFS, ext4, etc.)")
    total_bytes: int = Field(..., description="Total disk capacity in bytes")
    free_bytes: int = Field(..., description="Free disk capacity in bytes")
    used_bytes: int = Field(..., description="Used disk capacity in bytes")
    usage_percent: float = Field(..., description="Disk usage percentage")


class ProcessInfo(BaseModel):
    """System process summary."""
    pid: int = Field(..., description="Process ID")
    name: str = Field(..., description="Process executable name")
    cpu_percent: float = Field(0.0, description="Process CPU usage percentage")
    memory_bytes: int = Field(0, description="Process RAM consumption in bytes")
    status: str = Field("running", description="Current process status")


class SystemMetrics(BaseModel):
    """Consolidated real-time system metrics snapshot."""
    node_id: str = Field(..., description="Identifier of the node providing metrics")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of collection (UTC)")
    os_name: str = Field(..., description="Operating System name")
    os_version: str = Field(..., description="Operating System version")
    uptime_seconds: float = Field(..., description="System uptime in seconds")
    cpu: CPUMetrics = Field(..., description="CPU telemetry")
    memory: MemoryMetrics = Field(..., description="Memory telemetry")
    disks: List[DiskMetrics] = Field(default_factory=list, description="Storage telemetry")
    top_processes: List[ProcessInfo] = Field(default_factory=list, description="Top resource consuming processes")
