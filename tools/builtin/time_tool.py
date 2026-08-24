"""Time and date tool for JARVIS."""

from datetime import datetime, timezone
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel, ToolVisibility
from core.contracts.tool import BaseTool, ToolResult


class TimeArgs(BaseModel):
    timezone_offset: Optional[float] = Field(default=None, description="UTC offset in hours (e.g., -3 for BRT)")


class GetCurrentTimeTool(BaseTool):
    """Get the current date and time."""

    name: str = "get_current_time"
    description: str = "Get the current date, time, and timezone information."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = TimeArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        tz_offset = kwargs.get("timezone_offset")
        now = datetime.now(timezone.utc)

        if tz_offset is not None:
            from datetime import timedelta
            offset = timedelta(hours=tz_offset)
            local_time = now + offset
            tz_name = f"UTC{tz_offset:+.1f}"
        else:
            local_time = now
            tz_name = "UTC"

        return ToolResult.ok(
            data={
                "utc": now.isoformat(),
                "local": local_time.isoformat(),
                "timezone": tz_name,
                "date": local_time.strftime("%Y-%m-%d"),
                "time": local_time.strftime("%H:%M:%S"),
                "day_of_week": local_time.strftime("%A"),
                "timestamp": now.timestamp(),
            },
            security_level=self.security_level,
        )
