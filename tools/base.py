"""Tool system utilities and decorators."""

import time
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel, ValidationError

from core.contracts.enums import SecurityLevel, ToolVisibility
from core.contracts.tool import BaseTool, ToolMetadata, ToolResult


class FunctionalTool(BaseTool):
    """Wrapper that turns a standard Python async or sync function into a BaseTool."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        security_level: SecurityLevel = SecurityLevel.GREEN,
        visibility: ToolVisibility = ToolVisibility.LOCAL_ONLY,
        args_schema: Optional[Type[BaseModel]] = None,
        timeout_seconds: float = 30.0,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.security_level = security_level
        self.visibility = visibility
        self.args_schema = args_schema
        self.timeout_seconds = timeout_seconds

    async def execute(self, **kwargs: Any) -> ToolResult:
        start_time = time.perf_counter()
        try:
            # Validate parameters if schema provided
            if self.args_schema:
                validated_args = self.args_schema(**kwargs)
                kwargs = validated_args.model_dump()

            # Execute function (async or sync)
            import inspect
            if inspect.iscoroutinefunction(self.func):
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult.ok(data=result, security_level=self.security_level, execution_time_ms=duration_ms)

        except ValidationError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult.fail(
                error=f"Invalid arguments for tool '{self.name}': {e.errors()}",
                security_level=self.security_level,
                execution_time_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult.fail(
                error=f"Error executing tool '{self.name}': {str(e)}",
                security_level=self.security_level,
                execution_time_ms=duration_ms,
            )
