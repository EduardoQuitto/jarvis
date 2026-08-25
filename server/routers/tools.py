"""Tools execution and introspection API routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from core.contracts.tool import ToolMetadata
from security.auth import require_node_auth
from server.schemas import ToolExecutionRequest, ToolExecutionResponse
from tools.registry import get_tool_registry

router = APIRouter(prefix="/tools", tags=["Tools Engine"])


@router.get("", response_model=List[ToolMetadata])
async def list_available_tools(_token: str = Depends(require_node_auth)):
    """List all registered tools, their schemas, and security levels."""
    registry = get_tool_registry()
    return registry.list_tools()


@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(
    request: ToolExecutionRequest,
    _token: str = Depends(require_node_auth),
):
    """Execute a registered tool subject to security policy checks.

    Security: Uses source="operator" — confirmed=True is honored only for
    tools the operator is trusted to confirm.
    """
    registry = get_tool_registry()
    
    result = await registry.execute_tool(
        name=request.tool_name,
        parameters=request.parameters,
        confirmed=request.confirmed,
        source="operator",
    )

    return ToolExecutionResponse(
        success=result.success,
        data=result.data,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        security_level=result.security_level,
    )
