"""MCP (Model Context Protocol) Server — direct JSON-RPC 2.0 implementation.

Provides JARVIS tools and capabilities via the MCP protocol,
allowing external clients to interact with the agent system.
"""

import json
from typing import Any, Dict, List, Optional

from core.contracts.tool import ToolMetadata
from tools.registry import ToolRegistry
from core.logger import get_logger

logger = get_logger("jarvis.mcp_server")


class MCPServer:
    """MCP Server implementing JSON-RPC 2.0 for tool discovery and execution.

    This is a direct implementation — no external MCP SDK dependency.
    """

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self._registry = tool_registry

    def _get_registry(self) -> ToolRegistry:
        if self._registry is None:
            from tools.registry import get_tool_registry
            self._registry = get_tool_registry()
        return self._registry

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC 2.0 request."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "tools/list":
                result = await self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "ping":
                result = {}
            else:
                return self._error_response(req_id, -32601, f"Method not found: {method}")

            return self._success_response(req_id, result)

        except Exception as e:
            logger.error("MCP error handling %s: %s", method, str(e))
            return self._error_response(req_id, -32603, str(e))

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "jarvis-mcp",
                "version": "0.1.0",
            },
        }

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request — return all available tools."""
        registry = self._get_registry()
        tools = registry.list_tools()

        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": self._tool_metadata_to_schema(tool),
                }
                for tool in tools
            ]
        }

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request — execute a tool."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        registry = self._get_registry()
        tool = registry.get(tool_name)
        if not tool:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"error": f"Tool '{tool_name}' not found"}),
                    }
                ],
                "isError": True,
            }

        # Policy check — MCP never bypasses confirmation
        from security.policy_engine import PolicyEngine
        policy = PolicyEngine()
        decision = policy.evaluate(tool.metadata, arguments, confirmed=False)

        if not decision.allowed and decision.requires_confirmation:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "error": f"requires_confirmation",
                            "tool": tool_name,
                            "security_level": tool.metadata.security_level.value,
                            "reason": decision.reason,
                        }),
                    }
                ],
                "isError": True,
            }

        if not decision.allowed:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "error": f"denied",
                            "tool": tool_name,
                            "reason": decision.reason,
                        }),
                    }
                ],
                "isError": True,
            }

        # Execute the tool (GREEN or operator-approved)
        result = await registry.execute_tool(
            name=tool_name,
            parameters=arguments,
            confirmed=False,
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "success": result.success,
                        "data": result.data,
                        "error": result.error,
                    }),
                }
            ],
            "isError": not result.success,
        }

    def _tool_metadata_to_schema(self, tool: ToolMetadata) -> Dict[str, Any]:
        """Convert tool metadata to JSON Schema for MCP.

        ToolMetadata.parameters_schema is already a JSON Schema dict
        (generated by pydantic's model_json_schema()). MCP's inputSchema
        expects a JSON Schema, so we return it directly.
        """
        if tool.parameters_schema:
            return tool.parameters_schema

        return {"type": "object", "properties": {}, "required": []}

    def _success_response(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    def _error_response(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


# Global MCP server instance
_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """Access the global MCP server."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
