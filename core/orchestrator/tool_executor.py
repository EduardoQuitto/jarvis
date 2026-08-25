"""Tool Executor — bridges LLM tool calls to the ToolRegistry with policy enforcement.

Single authorization boundary: all tool executions pass through ToolRegistry.execute_tool(),
which delegates to PolicyEngine. The `source` parameter is propagated from the caller.
"""

from typing import Any, Dict, Optional

from core.contracts.enums import SecurityLevel
from core.contracts.tool import ToolResult
from core.contracts.orchestrator import OrchestratorToolResult
from core.llm.converters import create_tool_call_id
from tools.registry import ToolRegistry
from security.policy_engine import PolicyEngine
from core.logger import get_logger

logger = get_logger("jarvis.tool_executor")


class ToolExecutor:
    """Executes tool calls from the LLM through the existing ToolRegistry and PolicyEngine.

    Flow: LLM tool call -> validate tool exists -> PolicyEngine check -> ToolRegistry.execute -> ToolResult

    Security note: this executor never sets confirmed=True internally.
    Confirmed actions are always routed through the ConfirmationManager.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        policy_engine: Optional[PolicyEngine] = None,
    ):
        self._registry = registry
        self._policy_engine = policy_engine

    def _get_registry(self) -> ToolRegistry:
        if self._registry is None:
            from tools.registry import get_tool_registry
            self._registry = get_tool_registry()
        return self._registry

    def _get_policy(self) -> PolicyEngine:
        if self._policy_engine is None:
            self._policy_engine = PolicyEngine()
        return self._policy_engine

    async def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: Optional[str] = None,
        operator_direct: bool = False,
        source: str = "orchestrator",
    ) -> OrchestratorToolResult:
        """Execute a single tool call from the LLM.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool call arguments
            call_id: Unique call identifier
            operator_direct: True only when called from authenticated REST endpoint
            source: Origin of the request (propagated to ToolRegistry -> PolicyEngine)

        Returns an OrchestratorToolResult with the outcome.
        """
        if not call_id:
            call_id = create_tool_call_id()

        registry = self._get_registry()

        # Execute through the single authorization boundary
        result: ToolResult = await registry.execute_tool(
            name=tool_name,
            parameters=arguments,
            confirmed=operator_direct,
            source=source,
        )

        return OrchestratorToolResult(
            tool_name=tool_name,
            call_id=call_id,
            success=result.success,
            data=result.data,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
        )

    def get_available_tool_names(self) -> list:
        """Get names of all registered tools."""
        registry = self._get_registry()
        return [meta.name for meta in registry.list_tools()]
