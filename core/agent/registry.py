"""Agent Registry — tracks active and completed agents."""

from typing import Dict, List, Optional

from core.agent.agent import Agent
from core.contracts.enums import AgentStatus
from core.logger import get_logger

logger = get_logger("jarvis.agent_registry")


class AgentRegistry:
    """Registry for tracking agent lifecycle.

    Does NOT create agents — that's the AgentFactory's job.
    Only tracks agents that have been created.
    """

    def __init__(self):
        self._agents: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        """Register an agent."""
        self._agents[agent.agent_id] = agent
        logger.info("Registered agent: %s (%s)", agent.agent_id, agent.spec.agent_type)

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info("Unregistered agent: %s", agent_id)
            return True
        return False

    def get(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self, status: Optional[str] = None) -> List[Agent]:
        """List all agents, optionally filtered by status."""
        agents = list(self._agents.values())
        if status:
            agents = [a for a in agents if a.state.status == status]
        return agents

    def list_active_agents(self) -> List[Agent]:
        """List all non-terminal agents."""
        return [a for a in self._agents.values() if not a.is_terminal]

    def list_agents_for_goal(self, goal_id: str) -> List[Agent]:
        """List all agents associated with a goal."""
        return [
            a for a in self._agents.values()
            if a.spec.goal_id == goal_id
        ]

    @property
    def active_count(self) -> int:
        return len(self.list_active_agents())

    @property
    def total_count(self) -> int:
        return len(self._agents)


_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Access the global AgentRegistry instance."""
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry
