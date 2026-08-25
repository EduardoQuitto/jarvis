"""Agent — specialized executor with identity, permissions, and isolated context.

Security model:
- Permissions are set at creation and IMMUTABLE
- All tool execution goes through PolicyEngine with source="agent"
- Agent cannot set confirmed=True (PolicyEngine ignores it for untrusted sources)
- Agent cannot access LOCAL_ONLY tools unless can_access_local_only_tools=True
- AgentSecurityValidator is applied at execution time, not just at creation
- Agent uses an isolated ToolExecutor that validates permissions per tool call
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.contracts.agent import AgentSpec, AgentState, AgentResult, AgentPermission
from core.contracts.enums import AgentStatus, SecurityLevel, ToolVisibility
from core.contracts.orchestrator import OrchestratorRequest, OrchestratorResponse
from core.agent.security import AgentSecurityValidator, AgentSecurityError
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.agent")

# Source identifier for policy enforcement
SOURCE = "agent"


class AgentToolExecutor:
    """A ToolExecutor wrapper that validates agent permissions before each tool call.

    This ensures that even if the Orchestrator allows a tool, the agent's
    permissions are checked at execution time.
    """

    def __init__(self, spec: AgentSpec, tool_executor=None):
        self._spec = spec
        self._tool_executor = tool_executor

    def _get_executor(self):
        if self._tool_executor is None:
            from core.orchestrator.tool_executor import ToolExecutor
            self._tool_executor = ToolExecutor()
        return self._tool_executor

    async def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: Optional[str] = None,
        operator_direct: bool = False,
        source: str = "agent",
    ):
        """Execute a tool call with agent permission validation.

        Raises AgentSecurityError if agent is not allowed to use this tool.
        """
        # Validate agent can use this tool at execution time
        AgentSecurityValidator.validate_tool_execution(
            self._spec, tool_name, confirmed=operator_direct,
        )

        # Check visibility
        from tools.registry import get_tool_registry
        from tools import register_default_tools
        registry = get_tool_registry()
        register_default_tools(registry)
        tool = registry.get(tool_name)
        if tool:
            can_access = AgentSecurityValidator.can_access_tool(
                self._spec,
                tool_name,
                tool.metadata.visibility.value,
            )
            if not can_access:
                raise AgentSecurityError(
                    f"Agent '{self._spec.name}' cannot access tool '{tool_name}' "
                    f"(visibility: {tool.metadata.visibility.value}, "
                    f"local_only_access: {self._spec.permissions.can_access_local_only_tools})"
                )

        # Execute through the single authorization boundary
        executor = self._get_executor()
        return await executor.execute_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
            operator_direct=False,  # Agent can never confirm
            source=SOURCE,
        )


class Agent:
    """A specialized executor that runs within the JARVIS system.

    An Agent:
    - Has an identity (agent_id, type, name)
    - Has fixed permissions (tool_allowlist, provider_allowlist, etc.)
    - Has an isolated conversation session
    - Uses the Orchestrator for LLM+tool execution
    - Cannot grant itself new permissions
    - Cannot bypass PolicyEngine
    - Cannot confirm YELLOW/RED actions (unless explicitly permitted)

    Security model:
    - Permissions are set at creation and IMMUTABLE
    - All tool execution goes through PolicyEngine with source="agent"
    - Agent cannot set confirmed=True
    - Agent cannot access LOCAL_ONLY tools unless can_access_local_only_tools=True
    - AgentSecurityValidator is applied at execution time for every tool call
    """

    def __init__(self, spec: AgentSpec):
        self._spec = spec
        self._agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        self._state = AgentState(
            agent_id=self._agent_id,
            spec=spec,
            status=AgentStatus.PENDING,
        )
        self._orchestrator = None  # Lazy init
        self._event_bus = get_event_bus()
        self._start_time = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def spec(self) -> AgentSpec:
        return self._spec

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state.status in (
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
            AgentStatus.CANCELLED,
        )

    def _get_orchestrator(self):
        """Lazy-initialize the orchestrator for this agent.

        Uses an AgentToolExecutor that validates permissions per tool call.
        """
        if self._orchestrator is None:
            from core.orchestrator.engine import Orchestrator
            from core.orchestrator.tool_executor import ToolExecutor
            from core.orchestrator.confirmation import ConfirmationManager

            # Create an agent-specific ToolExecutor that validates permissions
            agent_executor = AgentToolExecutor(
                spec=self._spec,
                tool_executor=ToolExecutor(),
            )

            # Create an agent-specific confirmation manager (isolated)
            agent_confirmations = ConfirmationManager()

            self._orchestrator = Orchestrator(
                tool_executor=agent_executor,
                confirmation_manager=agent_confirmations,
            )
        return self._orchestrator

    def _filter_tools(self, tool_names: List[str]) -> List[str]:
        """Filter tool names by agent's permissions and visibility.

        If tool_allowlist is empty, no tools are allowed.
        If can_access_local_only_tools is False, only SHARED tools are allowed.
        """
        if not self._spec.permissions.tool_allowlist:
            return []

        allowed = set(self._spec.permissions.tool_allowlist)
        filtered = []
        for name in tool_names:
            if name not in allowed:
                continue
            # Also check visibility if we can get tool metadata
            from tools.registry import get_tool_registry
            registry = get_tool_registry()
            tool = registry.get(name)
            if tool and tool.metadata.visibility == ToolVisibility.LOCAL_ONLY:
                if not self._spec.permissions.can_access_local_only_tools:
                    continue
            filtered.append(name)
        return filtered

    def _check_permission(self, tool_name: str) -> bool:
        """Check if this agent is allowed to use a specific tool."""
        if not self._spec.permissions.tool_allowlist:
            return False
        return tool_name in self._spec.permissions.tool_allowlist

    async def execute(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Execute the agent's objective.

        This is the main entry point. The agent:
        1. Validates permissions at execution time
        2. Creates/uses an orchestrator session
        3. Sends the message to the orchestrator
        4. Returns the result

        The agent NEVER:
        - Sets confirmed=True on tool calls
        - Accesses tools outside its allowlist
        - Modifies its own permissions
        - Bypasses PolicyEngine
        """
        if self._state.status == AgentStatus.RUNNING:
            return AgentResult(
                agent_id=self._agent_id,
                agent_type=self._spec.agent_type,
                status=AgentStatus.FAILED,
                error="Agent is already running",
            )

        # Validate spec at execution time
        try:
            AgentSecurityValidator.validate_spec(self._spec)
        except AgentSecurityError as e:
            return AgentResult(
                agent_id=self._agent_id,
                agent_type=self._spec.agent_type,
                status=AgentStatus.FAILED,
                error=f"Security validation failed: {e}",
            )

        self._state.status = AgentStatus.RUNNING
        self._state.started_at = datetime.now(timezone.utc)
        self._start_time = time.monotonic()

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.AGENT_STARTED,
            source=f"agent.{self._spec.agent_type}",
            data={"agent_id": self._agent_id, "objective": self._spec.objective[:100]},
        ))

        try:
            orchestrator = self._get_orchestrator()

            # Create a session for this agent
            if not session_id:
                session_id = await orchestrator._conversation.create_session(
                    title=f"Agent: {self._spec.name}",
                    device_id=f"agent-{self._agent_id}",
                )
            self._state.session_id = session_id

            # Build the message with agent context
            agent_context = (
                f"[Agent: {self._spec.name} | Type: {self._spec.agent_type}]\n"
                f"Objective: {self._spec.objective}\n"
                f"Context: {self._spec.context}\n\n"
                f"User request: {message}"
            )

            # Create orchestrator request
            request = OrchestratorRequest(
                message=agent_context,
                session_id=session_id,
                device_id=f"agent-{self._agent_id}",
            )

            # Execute via orchestrator (which handles LLM + tools + policy)
            response = await orchestrator.process_message(request)

            # Track iterations
            self._state.iterations_used = response.iterations_used

            # Track tools called
            for tr in response.tool_calls_made:
                self._state.tools_called.append(tr.tool_name)

            # Check duration limit
            duration = time.monotonic() - self._start_time
            if duration > self._spec.permissions.max_duration_seconds:
                self._state.status = AgentStatus.FAILED
                self._state.error = f"Execution time exceeded {self._spec.permissions.max_duration_seconds}s"
                return self._build_result(AgentStatus.FAILED, self._state.error)

            # Check iteration limit
            if response.iterations_used >= self._spec.permissions.max_iterations:
                self._state.status = AgentStatus.FAILED
                self._state.error = f"Iteration limit reached ({self._spec.permissions.max_iterations})"
                return self._build_result(AgentStatus.FAILED, self._state.error)

            if response.error:
                self._state.status = AgentStatus.FAILED
                self._state.error = response.error
                return self._build_result(AgentStatus.FAILED, response.error)

            # Success
            self._state.status = AgentStatus.COMPLETED
            self._state.completed_at = datetime.now(timezone.utc)

            result = self._build_result(AgentStatus.COMPLETED, result_text=response.response_text)

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.AGENT_COMPLETED,
                source=f"agent.{self._spec.agent_type}",
                data={
                    "agent_id": self._agent_id,
                    "result": response.response_text[:200],
                    "iterations": response.iterations_used,
                },
            ))

            return result

        except Exception as e:
            self._state.status = AgentStatus.FAILED
            self._state.error = str(e)
            self._state.completed_at = datetime.now(timezone.utc)

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.AGENT_FAILED,
                source=f"agent.{self._spec.agent_type}",
                data={"agent_id": self._agent_id, "error": str(e)},
            ))

            return self._build_result(AgentStatus.FAILED, str(e))

    def _build_result(
        self,
        status: AgentStatus,
        result_text: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AgentResult:
        """Build an AgentResult from current state."""
        duration_ms = 0.0
        if self._start_time:
            duration_ms = (time.monotonic() - self._start_time) * 1000

        return AgentResult(
            agent_id=self._agent_id,
            agent_type=self._spec.agent_type,
            status=status.value,
            result=result_text,
            steps_executed=len(self._state.tools_called),
            tools_used=self._state.tools_called,
            duration_ms=duration_ms,
            error=error,
        )

    async def cancel(self) -> None:
        """Cancel this agent's execution."""
        if self.is_terminal:
            return

        self._state.status = AgentStatus.CANCELLED
        self._state.completed_at = datetime.now(timezone.utc)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.AGENT_FAILED,
            source=f"agent.{self._spec.agent_type}",
            data={"agent_id": self._agent_id, "error": "Cancelled by user"},
        ))
