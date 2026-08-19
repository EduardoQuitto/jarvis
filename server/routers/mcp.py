"""MCP API Router — /api/mcp endpoints for Model Context Protocol."""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.mcp.server import get_mcp_server
from core.logger import get_logger

logger = get_logger("jarvis.api.mcp")

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = {}
    id: Any = None


@router.post("/", response_model=Dict[str, Any])
async def handle_mcp_request(request: MCPRequest) -> Dict[str, Any]:
    """Handle an MCP JSON-RPC 2.0 request."""
    try:
        server = get_mcp_server()
        result = await server.handle_request({
            "jsonrpc": request.jsonrpc,
            "method": request.method,
            "params": request.params,
            "id": request.id,
        })
        return result
    except Exception as e:
        logger.error("MCP request error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools")
async def list_mcp_tools() -> Dict[str, Any]:
    """List all available MCP tools."""
    try:
        server = get_mcp_server()
        result = await server.handle_request({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
        })
        return result.get("result", {})
    except Exception as e:
        logger.error("MCP tools list error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
