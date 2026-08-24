"""Agent Factory — creates specialized agents from controlled specifications."""

from typing import Any, Dict, List, Optional

from core.agent.agent import Agent
from core.agent.registry import AgentRegistry, get_agent_registry
from core.contracts.agent import AgentSpec, AgentPermission
from core.contracts.enums import SecurityLevel
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.agent_factory")


class AgentValidationError(Exception):
    """Raised when an agent specification fails validation."""
    pass


class AgentFactory:
    """Creates agents from validated specifications.

    Security rules:
    - tool_allowlist is validated against registered tools
    - provider_allowlist is validated against registered providers
    - Agent CANNOT grant itself can_confirm_actions=True unless explicitly set
    - Agent CANNOT access LOCAL_ONLY tools unless can_access_local_only_tools=True
    - Overrides that bypass security are blocked
    """

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self._registry = registry or get_agent_registry()
        self._event_bus = get_event_bus()

    def create_agent(
        self,
        agent_type: str,
        name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        tool_allowlist: Optional[List[str]] = None,
        provider_allowlist: Optional[List[str]] = None,
        max_iterations: int = 10,
        max_duration_seconds: float = 300.0,
        can_confirm_actions: bool = False,
        can_access_local_only_tools: bool = False,
        provider_name: Optional[str] = None,
        goal_id: Optional[str] = None,
        task_id: Optional[str] = None,
        description: str = "",
    ) -> Agent:
        """Create a new agent from a controlled specification.

        Args:
            agent_type: Type of agent (research, developer, analyst, critic, custom)
            name: Human-readable name
            objective: What the agent should achieve
            context: Additional context
            tool_allowlist: Tools this agent may use (validated against registry)
            provider_allowlist: Providers this agent may use (validated against registry)
            max_iterations: Max LLM loop iterations
            max_duration_seconds: Max execution time
            can_confirm_actions: Whether agent can confirm YELLOW/RED actions
            can_access_local_only_tools: Whether agent can see LOCAL_ONLY tools
            provider_name: Preferred provider (None = auto-select)
            goal_id: Parent goal ID
            task_id: Parent task ID
            description: Detailed description

        Returns:
            Created Agent instance

        Raises:
            AgentValidationError: If specification fails validation
        """
        # Validate agent_type
        valid_types = {"research", "developer", "analyst", "critic", "custom"}
        if agent_type not in valid_types:
            raise AgentValidationError(
                f"Invalid agent_type: {agent_type}. Must be one of: {valid_types}"
            )

        # Validate tool_allowlist against registered tools
        if tool_allowlist:
            from tools.registry import get_tool_registry
            from tools import register_default_tools
            tool_registry = get_tool_registry()
            register_default_tools(tool_registry)  # Ensure tools are registered
            registered_tools = {t.name for t in tool_registry.list_tools()}
            invalid_tools = set(tool_allowlist) - registered_tools
            if invalid_tools:
                raise AgentValidationError(
                    f"Tools not registered: {invalid_tools}. "
                    f"Available tools: {registered_tools}"
                )

        # Validate provider_allowlist against registered providers
        if provider_allowlist:
            from core.llm.registry import get_provider_registry
            provider_registry = get_provider_registry()
            registered_providers = {p.name for p in provider_registry.list_providers()}
            invalid_providers = set(provider_allowlist) - registered_providers
            if invalid_providers:
                raise AgentValidationError(
                    f"Providers not registered: {invalid_providers}. "
                    f"Available providers: {registered_providers}"
                )

        # Create permissions (immutable after creation)
        permissions = AgentPermission(
            tool_allowlist=tool_allowlist or [],
            provider_allowlist=provider_allowlist or [],
            max_iterations=max_iterations,
            max_duration_seconds=max_duration_seconds,
            can_confirm_actions=can_confirm_actions,
            can_access_local_only_tools=can_access_local_only_tools,
        )

        # Create spec
        spec = AgentSpec(
            agent_type=agent_type,
            name=name,
            objective=objective,
            description=description,
            context=context or {},
            permissions=permissions,
            goal_id=goal_id,
            task_id=task_id,
            provider_name=provider_name,
        )

        # Create agent
        agent = Agent(spec)

        # Register
        self._registry.register(agent)

        logger.info(
            "Created agent %s (%s): %s",
            agent.agent_id, agent_type, name,
        )

        # Note: Event publishing is async. The factory is sync for convenience.
        # Agents publish their own AGENT_STARTED/COMPLETED events when execute() is called.

        return agent

    def create_research_agent(
        self,
        name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> Agent:
        """Create a ResearchAgent — for gathering information and analysis."""
        return self.create_agent(
            agent_type="research",
            name=name,
            objective=objective,
            context=context,
            tool_allowlist=["echo", "get_current_time", "web_search", "fetch_url"],
            provider_allowlist=[],
            max_iterations=10,
            max_duration_seconds=120.0,
            can_confirm_actions=False,
            can_access_local_only_tools=False,
            goal_id=goal_id,
            description="Research agent for information gathering and analysis",
        )

    def create_developer_agent(
        self,
        name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> Agent:
        """Create a DeveloperAgent — for code-related tasks with file access."""
        return self.create_agent(
            agent_type="developer",
            name=name,
            objective=objective,
            context=context,
            tool_allowlist=[
                "echo", "get_current_time", "web_search", "fetch_url",
                "read_file", "write_file", "list_dir",
            ],
            provider_allowlist=[],
            max_iterations=15,
            max_duration_seconds=300.0,
            can_confirm_actions=False,
            can_access_local_only_tools=True,
            goal_id=goal_id,
            description="Developer agent for code reading, writing, and analysis",
        )

    def create_analyst_agent(
        self,
        name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> Agent:
        """Create an AnalystAgent — for data analysis and metrics."""
        return self.create_agent(
            agent_type="analyst",
            name=name,
            objective=objective,
            context=context,
            tool_allowlist=[
                "echo", "get_current_time", "get_system_metrics", "list_processes",
            ],
            provider_allowlist=[],
            max_iterations=10,
            max_duration_seconds=120.0,
            can_confirm_actions=False,
            can_access_local_only_tools=True,
            goal_id=goal_id,
            description="Analyst agent for system metrics and data analysis",
        )

    def create_critic_agent(
        self,
        name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> Agent:
        """Create a CriticAgent — for reviewing and validating work."""
        return self.create_agent(
            agent_type="critic",
            name=name,
            objective=objective,
            context=context,
            tool_allowlist=["echo", "get_current_time"],
            provider_allowlist=[],
            max_iterations=5,
            max_duration_seconds=60.0,
            can_confirm_actions=False,
            can_access_local_only_tools=False,
            goal_id=goal_id,
            description="Critic agent for reviewing and validating work products",
        )


_agent_factory: Optional[AgentFactory] = None


def get_agent_factory() -> AgentFactory:
    """Access the global AgentFactory instance."""
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()
    return _agent_factory
