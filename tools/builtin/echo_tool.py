"""Echo / Ping tool for testing connectivity and registry functionality."""

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import ParamKind, SecurityLevel, ToolVisibility
from core.contracts.tool import BaseTool, ToolResult


class EchoArgs(BaseModel):
    message: str = Field(..., description="Message string to echo back")


class EchoTool(BaseTool):
    """Simple diagnostic tool that returns the provided message."""

    name: str = "echo"
    description: str = "Echo back the input message for diagnostics and connectivity checks."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = EchoArgs
    # Echoed text is returned as data and never reaches a shell.
    param_kinds: Dict[str, ParamKind] = {"message": ParamKind.FREE_TEXT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        message = kwargs.get("message", "")
        return ToolResult.ok(data={"echo": message}, security_level=self.security_level)
