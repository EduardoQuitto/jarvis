"""Tool Executor — bridges LLM tool calls to the ToolRegistry with policy enforcement."""

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

    Flow: LLM tool call → validate tool exists → PolicyEngine check → ToolRegistry.execute → ToolResult
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
        confirmed: bool = False,
    ) -> OrchestratorToolResult:
        """Execute a single tool call from the LLM.

        Returns an OrchestratorToolResult with the outcome.
        """
        if not call_id:
            call_id = create_tool_call_id()

        registry = self._get_registry()
        policy = self._get_policy()

        # 1. Validate tool exists
        tool = registry.get(tool_name)
        if not tool:
            logger.warning("Tool '%s' not found in registry", tool_name)
            return OrchestratorToolResult(
                tool_name=tool_name,
                call_id=call_id,
                success=False,
                error=f"Tool '{tool_name}' is not registered.",
            )

        # 2. Policy check
        decision = policy.evaluate(tool.metadata, arguments, confirmed=confirmed)
        if not decision.allowed:
            logger.info("Policy denied tool '%s': %s", tool_name, decision.reason)
            return OrchestratorToolResult(
                tool_name=tool_name,
                call_id=call_id,
                success=False,
                error=f"Policy Denied: {decision.reason}",
            )

        # 3. Execute
        logger.info("Executing tool '%s' (confirmed=%s)", tool_name, confirmed)
        result: ToolResult = await registry.execute_tool(
            name=tool_name,
            parameters=arguments,
            confirmed=confirmed,
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
