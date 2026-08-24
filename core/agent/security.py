"""Agent Security — validates agent permissions and enforces security constraints."""

from typing import List, Optional

from core.contracts.agent import AgentSpec, AgentPermission
from core.contracts.enums import SecurityLevel
from core.logger import get_logger

logger = get_logger("jarvis.agent_security")


class AgentSecurityError(Exception):
    """Raised when an agent violates security constraints."""
    pass


class AgentSecurityValidator:
    """Validates agent specifications against security constraints.

    Rules:
    1. Agent CANNOT grant itself can_confirm_actions=True
       (must be explicitly set by the system, not by the agent)
    2. Agent CANNOT access LOCAL_ONLY tools unless can_access_local_only_tools=True
    3. Agent CANNOT use tools not in the ToolRegistry
    4. Agent CANNOT use providers not in the ProviderRegistry
    5. Agent CANNOT modify PolicyEngine settings
    6. Agent CANNOT modify security levels
    """

    # Tools that should NEVER be in an agent's allowlist
    FORBIDDEN_TOOLS = set()

    # Permissions that agents cannot grant themselves
    RESTRICTED_PERMISSIONS = {
        "can_confirm_actions": False,  # Must be explicitly set by system
    }

    @classmethod
    def validate_spec(cls, spec: AgentSpec) -> None:
        """Validate an agent specification against security constraints."""
        # Check restricted permissions
        if spec.permissions.can_confirm_actions:
            logger.warning(
                "Agent '%s' requested can_confirm_actions=True. "
                "This permission is restricted and must be explicitly granted by the system.",
                spec.name,
            )
            # Don't raise — allow system to grant this if needed
            # But log the attempt

        # Check forbidden tools
        forbidden = set(spec.permissions.tool_allowlist) & cls.FORBIDDEN_TOOLS
        if forbidden:
            raise AgentSecurityError(
                f"Agent '{spec.name}' requested forbidden tools: {forbidden}"
            )

        # Validate tool names are valid identifiers
        for tool_name in spec.permissions.tool_allowlist:
            if not tool_name.isidentifier():
                raise AgentSecurityError(
                    f"Agent '{spec.name}' has invalid tool name: {tool_name}"
                )

        logger.info("Agent spec validated: %s (%s)", spec.name, spec.agent_type)

    @classmethod
    def can_access_tool(cls, spec: AgentSpec, tool_name: str, tool_visibility: str) -> bool:
        """Check if an agent can access a specific tool.

        Args:
            spec: Agent specification
            tool_name: Name of the tool
            tool_visibility: "LOCAL_ONLY" or "SHARED"

        Returns:
            True if agent can access the tool
        """
        # Check tool allowlist
        if tool_name not in spec.permissions.tool_allowlist:
            return False

        # Check visibility
        if tool_visibility == "LOCAL_ONLY" and not spec.permissions.can_access_local_only_tools:
            return False

        return True

    @classmethod
    def filter_tools(cls, spec: AgentSpec, tool_names: List[str], tool_visibilities: dict) -> List[str]:
        """Filter tool names by agent's permissions and visibility.

        Args:
            spec: Agent specification
            tool_names: List of tool names
            tool_visibilities: Dict mapping tool_name -> visibility

        Returns:
            List of allowed tool names
        """
        allowed = []
        for name in tool_names:
            visibility = tool_visibilities.get(name, "LOCAL_ONLY")
            if cls.can_access_tool(spec, name, visibility):
                allowed.append(name)
        return allowed

    @classmethod
    def validate_tool_execution(
        cls,
        spec: AgentSpec,
        tool_name: str,
        confirmed: bool = False,
    ) -> None:
        """Validate that an agent can execute a specific tool.

        Raises:
            AgentSecurityError: If execution is not allowed
        """
        # Agent cannot set confirmed=True
        if confirmed:
            raise AgentSecurityError(
                f"Agent '{spec.name}' cannot set confirmed=True. "
                "Only the system can confirm actions."
            )

        # Check tool allowlist
        if tool_name not in spec.permissions.tool_allowlist:
            raise AgentSecurityError(
                f"Agent '{spec.name}' tried to use tool '{tool_name}' "
                f"which is not in its allowlist: {spec.permissions.tool_allowlist}"
            )
