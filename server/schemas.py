"""API Request and Response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.contracts.enums import SecurityLevel
from core.contracts.telemetry import SystemMetrics
from core.contracts.tool import ToolMetadata


class ToolExecutionRequest(BaseModel):
    """Payload to request tool execution."""
    tool_name: str = Field(..., description="Target tool name to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters matching tool schema")
    confirmed: bool = Field(default=False, description="Explicit confirmation flag for yellow/red tools")


class ToolExecutionResponse(BaseModel):
    """Standardized API response for tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    security_level: SecurityLevel


class HealthResponse(BaseModel):
    """Overall node health response."""
    status: str
    node_id: str
    node_role: str
    registered_tools_count: int
    system: SystemMetrics
    gpu: Optional[Dict[str, Any]] = None
