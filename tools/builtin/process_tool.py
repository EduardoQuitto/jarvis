"""Process query tools."""

import time
from typing import Any, List, Optional, Type
from pydantic import BaseModel, Field
import psutil

from core.contracts.enums import SecurityLevel
from core.contracts.telemetry import ProcessInfo
from core.contracts.tool import BaseTool, ToolResult


class ListProcessesArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of processes to return")
    sort_by: str = Field(default="memory", description="Sort criteria: memory, cpu, name")


class ListProcessesTool(BaseTool):
    """Tool that lists active system processes."""

    name: str = "list_processes"
    description: str = "List running system processes with resource consumption."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = ListProcessesArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        start = time.perf_counter()
        limit = kwargs.get("limit", 20)
        sort_by = kwargs.get("sort_by", "memory")

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

        sliced = [p.model_dump() for p in processes[:limit]]
        duration_ms = (time.perf_counter() - start) * 1000.0
        return ToolResult.ok(data={"processes": sliced, "total_running": len(processes)}, security_level=self.security_level, execution_time_ms=duration_ms)
