"""Contracts and base definitions for the Tool System."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel, ToolVisibility


class ToolResult(BaseModel):
    """Standardized output returned by any tool execution."""
    success: bool = Field(..., description="Whether the tool execution succeeded")
    data: Any = Field(default=None, description="Payload data returned by the tool")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    execution_time_ms: float = Field(default=0.0, description="Duration of tool execution in milliseconds")
    security_level: SecurityLevel = Field(..., description="Security classification of the executed tool")

    @classmethod
    def ok(cls, data: Any, security_level: SecurityLevel = SecurityLevel.GREEN, execution_time_ms: float = 0.0) -> "ToolResult":
        """Convenience constructor for successful results."""
        return cls(
            success=True,
            data=data,
            error=None,
            execution_time_ms=execution_time_ms,
            security_level=security_level,
        )

    @classmethod
    def fail(cls, error: str, security_level: SecurityLevel = SecurityLevel.GREEN, execution_time_ms: float = 0.0) -> "ToolResult":
        """Convenience constructor for failed results."""
        return cls(
            success=False,
            data=None,
            error=error,
            execution_time_ms=execution_time_ms,
            security_level=security_level,
        )


class ToolMetadata(BaseModel):
    """Metadata describing a tool's capabilities, schema, and security level."""
    name: str = Field(..., description="Unique snake_case identifier of the tool")
    description: str = Field(..., description="Clear human-readable description of what the tool does")
    security_level: SecurityLevel = Field(default=SecurityLevel.GREEN, description="Security level classification")
    visibility: ToolVisibility = Field(default=ToolVisibility.LOCAL_ONLY, description="Provider visibility: LOCAL_ONLY or SHARED")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema of acceptable parameters")
    timeout_seconds: float = Field(default=30.0, description="Maximum execution timeout in seconds")


class BaseTool(ABC):
    """Abstract Base Class that every JARVIS tool must implement."""

    name: str
    description: str
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.LOCAL_ONLY
    args_schema: Optional[Type[BaseModel]] = None
    timeout_seconds: float = 30.0

    @property
    def metadata(self) -> ToolMetadata:
        """Generate metadata for registration and introspection."""
        schema = self.args_schema.model_json_schema() if self.args_schema else {}
        return ToolMetadata(
            name=self.name,
            description=self.description,
            security_level=self.security_level,
            visibility=self.visibility,
            parameters_schema=schema,
            timeout_seconds=self.timeout_seconds,
        )

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given validated arguments."""
        pass
