"""Security Policy Engine — single authorization boundary for all tool executions.

Every tool call, regardless of origin (user, LLM, MCP, agent, planner, step executor),
must pass through this engine. The `source` parameter determines what is permitted.

Sources:
  - "operator": Authenticated REST call (require_node_auth). Can confirm YELLOW and RED.
  - "orchestrator": LLM-driven agentic loop. Can confirm YELLOW only via ConfirmationManager.
  - "mcp": External MCP client. Cannot confirm anything. LOCAL_ONLY tools blocked.
  - "plan_executor": Deterministic plan execution. Never pre-confirmed.
  - "step_executor": Direct tool execution from task step. Never pre-confirmed.
  - "agent": Agent execution. Cannot confirm. Visibility-restricted.
"""

from typing import Any, Dict, Optional
from core.contracts.enums import SecurityLevel
from core.contracts.tool import ToolMetadata
from core.config import get_settings
from security.allowlist import AllowlistValidator, SecurityValidationError


class PolicyDecision:
    """Outcome of a policy evaluation."""
    def __init__(
        self,
        allowed: bool,
        reason: str,
        requires_confirmation: bool = False,
        requires_explicit_operator: bool = False,
    ):
        self.allowed = allowed
        self.reason = reason
        self.requires_confirmation = requires_confirmation
        self.requires_explicit_operator = requires_explicit_operator

    @classmethod
    def allow(cls, reason: str = "Authorized") -> "PolicyDecision":
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> "PolicyDecision":
        return cls(allowed=False, reason=reason)

    @classmethod
    def need_confirmation(cls, reason: str) -> "PolicyDecision":
        return cls(allowed=False, reason=reason, requires_confirmation=True)

    @classmethod
    def need_operator(cls, reason: str) -> "PolicyDecision":
        """RED actions require explicit operator (authenticated REST) confirmation."""
        return cls(allowed=False, reason=reason, requires_confirmation=True, requires_explicit_operator=True)


# Sources that can NEVER confirm actions (confirmed=True is ignored)
UNTRUSTED_SOURCES = frozenset({"mcp", "plan_executor", "step_executor", "agent"})

# Sources that can confirm YELLOW but NOT RED
YELLOW_CAPABLE_SOURCES = frozenset({"orchestrator"})

# Sources that can confirm both YELLOW and RED
OPERATOR_SOURCES = frozenset({"operator"})


class PolicyEngine:
    """Enforces safety, confirmation levels, and input parameter sanitization.

    Single authorization boundary: ALL tool executions must pass through evaluate().
    The `source` parameter enforces trust boundaries per origin.
    """

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    def evaluate(
        self,
        tool: ToolMetadata,
        parameters: Dict[str, Any],
        confirmed: bool = False,
        source: str = "orchestrator",
    ) -> PolicyDecision:
        """Evaluate whether a tool call is permitted according to safety rules.

        Args:
            tool: Tool metadata including security level
            parameters: Tool call parameters
            confirmed: Whether the caller claims confirmation (ignored for untrusted sources)
            source: Origin of the request ("operator", "orchestrator", "mcp",
                    "plan_executor", "step_executor", "agent")

        Returns:
            PolicyDecision with allowed, reason, and confirmation requirements
        """
        settings = get_settings()

        # For untrusted sources, confirmed=True is silently ignored
        effective_confirmed = confirmed and source not in UNTRUSTED_SOURCES

        # Step 1: Check parameter safety against shell injection / forbidden strings
        for param_name, param_val in parameters.items():
            if isinstance(param_val, str):
                try:
                    self.validator.sanitize_input_string(param_val)
                except SecurityValidationError as e:
                    return PolicyDecision.deny(
                        f"Parameter '{param_name}' failed security sanitization: {e}"
                    )

        # Step 2: Check security levels
        if tool.security_level == SecurityLevel.GREEN:
            return PolicyDecision.allow("Action is classified GREEN and authorized automatically.")

        if tool.security_level == SecurityLevel.YELLOW:
            if source in UNTRUSTED_SOURCES:
                # MCP, planner, step executor, agent cannot confirm YELLOW
                return PolicyDecision.need_confirmation(
                    f"Tool '{tool.name}' is classified YELLOW. "
                    f"Source '{source}' cannot confirm actions. Confirmation required."
                )
            if settings.confirm_yellow_actions and not effective_confirmed:
                return PolicyDecision.need_confirmation(
                    f"Tool '{tool.name}' is classified YELLOW (requires user confirmation before execution)."
                )
            return PolicyDecision.allow(
                "Action is classified YELLOW and user confirmation was provided."
            )

        if tool.security_level == SecurityLevel.RED:
            if source in UNTRUSTED_SOURCES:
                # MCP, planner, step executor, agent CANNOT confirm RED
                return PolicyDecision.need_operator(
                    f"Tool '{tool.name}' is classified RED. "
                    f"Source '{source}' cannot confirm RED actions. "
                    f"Explicit operator (authenticated REST) confirmation required."
                )
            if source in YELLOW_CAPABLE_SOURCES:
                # Orchestrator can confirm YELLOW but NOT RED
                return PolicyDecision.need_operator(
                    f"Tool '{tool.name}' is classified RED. "
                    f"The orchestrator cannot confirm RED actions. "
                    f"Explicit operator (authenticated REST) confirmation required."
                )
            if settings.confirm_red_actions and not effective_confirmed:
                return PolicyDecision.need_operator(
                    f"Tool '{tool.name}' is classified RED (requires explicit high-privilege confirmation)."
                )
            if source in OPERATOR_SOURCES:
                return PolicyDecision.allow(
                    "Action is classified RED and explicit operator confirmation was provided."
                )
            return PolicyDecision.deny(
                f"Tool '{tool.name}' is classified RED. "
                f"Source '{source}' is not authorized to confirm RED actions."
            )

        return PolicyDecision.deny(f"Unknown security level for tool '{tool.name}'.")

    def evaluate_tool_visibility(
        self,
        tool: ToolMetadata,
        source: str,
        agent_can_access_local_only: bool = False,
    ) -> bool:
        """Check if a tool's visibility is accessible from the given source.

        Args:
            tool: Tool metadata
            source: Origin of the request
            agent_can_access_local_only: For agent source, whether agent has local-only permission

        Returns:
            True if the tool is accessible from this source
        """
        from core.contracts.enums import ToolVisibility

        if tool.visibility == ToolVisibility.SHARED:
            return True

        # LOCAL_ONLY tools
        if source == "mcp":
            return False  # MCP clients never see LOCAL_ONLY tools
        if source == "agent" and not agent_can_access_local_only:
            return False
        # Other sources (operator, orchestrator, plan_executor, step_executor) can see LOCAL_ONLY
        return True
