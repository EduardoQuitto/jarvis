"""Central Tool Registry with policy enforcement.

All tool executions MUST pass through execute_tool(), which enforces
the single authorization boundary via PolicyEngine.
"""

import time
from typing import Any, Dict, List, Optional
from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolMetadata, ToolResult
from security.policy_engine import PolicyEngine


class ToolNotFoundError(Exception):
    """Raised when a requested tool is not registered."""
    pass


class ToolRegistry:
    """Registry maintaining available tools and mediating their secure execution.

    Single authorization boundary: execute_tool() is the ONLY way to run tools.
    The `source` parameter is propagated to PolicyEngine for trust enforcement.
    """

    def __init__(self, policy_engine: Optional[PolicyEngine] = None):
        self._tools: Dict[str, BaseTool] = {}
        self.policy_engine = policy_engine or PolicyEngine()

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name or not tool.name.isidentifier():
            raise ValueError(f"Tool name '{tool.name}' must be a valid identifier.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolMetadata]:
        """List metadata for all registered tools."""
        return [tool.metadata for tool in self._tools.values()]

    def list_tools_for_source(self, source: str) -> List[ToolMetadata]:
        """List tools visible to a specific source (respects ToolVisibility)."""
        all_tools = self.list_tools()
        if source == "mcp":
            from core.contracts.enums import ToolVisibility
            return [t for t in all_tools if t.visibility == ToolVisibility.SHARED]
        return all_tools

    async def execute_tool(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        source: str = "orchestrator",
    ) -> ToolResult:
        """Evaluate policy and execute the requested tool securely.

        Args:
            name: Tool name
            parameters: Tool call parameters
            claimed_confirmation: Whether the caller claims confirmation
            source: Origin of the request (propagated to PolicyEngine)

        Returns:
            ToolResult with outcome
        """
        parameters = parameters or {}
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(
                error=f"Tool '{name}' is not registered in the system.",
                security_level=SecurityLevel.GREEN,
            )

        # Check tool visibility for this source
        if not self.policy_engine.evaluate_tool_visibility(tool.metadata, source):
            return ToolResult.fail(
                error=f"Tool '{name}' is not accessible from source '{source}' "
                      f"(visibility: {tool.metadata.visibility.value}).",
                security_level=tool.security_level,
            )

        # Evaluate policy engine — single authorization boundary
        decision = self.policy_engine.evaluate(
            tool.metadata, parameters, confirmed=confirmed, source=source,
        )
        if not decision.allowed:
            return ToolResult.fail(
                error=f"Policy Denied: {decision.reason}",
                security_level=tool.security_level,
            )

        # Execute tool
        try:
            return await tool.execute(**parameters)
        except Exception as e:
            return ToolResult.fail(
                error=f"Unhandled exception during tool '{name}' execution: {str(e)}",
                security_level=tool.security_level,
            )


# Global singleton registry
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Access the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
