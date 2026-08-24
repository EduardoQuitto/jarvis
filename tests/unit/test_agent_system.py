"""Tests for Agent System — agent creation, permissions, and security."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent.agent import Agent
from core.agent.factory import AgentFactory, AgentValidationError
from core.agent.registry import AgentRegistry
from core.agent.security import AgentSecurityValidator, AgentSecurityError
from core.contracts.agent import AgentSpec, AgentPermission
from core.contracts.enums import AgentStatus


class TestAgent:
    """Agent unit tests."""

    def test_agent_creation(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test objective",
            permissions=AgentPermission(
                tool_allowlist=["echo"],
                max_iterations=5,
            ),
        )
        agent = Agent(spec)
        assert agent.agent_id.startswith("agent-")
        assert agent.spec.agent_type == "research"
        assert agent.state.status == AgentStatus.PENDING
        assert not agent.is_terminal

    def test_agent_is_terminal(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test",
        )
        agent = Agent(spec)
        assert not agent.is_terminal

        agent._state.status = AgentStatus.COMPLETED
        assert agent.is_terminal

    def test_agent_filter_tools(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo", "web_search"],
            ),
        )
        agent = Agent(spec)
        filtered = agent._filter_tools(["echo", "web_search", "read_file", "write_file"])
        assert filtered == ["echo", "web_search"]

    def test_agent_check_permission(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo"],
            ),
        )
        agent = Agent(spec)
        assert agent._check_permission("echo") is True
        assert agent._check_permission("read_file") is False

    def test_agent_empty_allowlist_blocks_all(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=[],
            ),
        )
        agent = Agent(spec)
        assert agent._check_permission("echo") is False
        assert agent._filter_tools(["echo"]) == []


class TestAgentSecurity:
    """Agent security validation tests."""

    def test_validate_spec_valid(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test Agent",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo", "web_search"],
            ),
        )
        AgentSecurityValidator.validate_spec(spec)  # Should not raise

    def test_validate_spec_forbidden_tool(self):
        spec = AgentSpec(
            agent_type="custom",
            name="Bad Agent",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo", "nonexistent_tool"],
            ),
        )
        # Should not raise — forbidden tools are checked at execution time
        AgentSecurityValidator.validate_spec(spec)

    def test_can_access_tool_allowed(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo", "web_search"],
                can_access_local_only_tools=False,
            ),
        )
        assert AgentSecurityValidator.can_access_tool(spec, "echo", "SHARED") is True
        assert AgentSecurityValidator.can_access_tool(spec, "web_search", "SHARED") is True

    def test_can_access_tool_not_in_allowlist(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo"],
            ),
        )
        assert AgentSecurityValidator.can_access_tool(spec, "read_file", "SHARED") is False

    def test_can_access_tool_local_only_blocked(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["read_file"],
                can_access_local_only_tools=False,
            ),
        )
        assert AgentSecurityValidator.can_access_tool(spec, "read_file", "LOCAL_ONLY") is False

    def test_can_access_tool_local_only_allowed(self):
        spec = AgentSpec(
            agent_type="developer",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["read_file"],
                can_access_local_only_tools=True,
            ),
        )
        assert AgentSecurityValidator.can_access_tool(spec, "read_file", "LOCAL_ONLY") is True

    def test_filter_tools(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo", "web_search"],
            ),
        )
        visibilities = {
            "echo": "SHARED",
            "web_search": "SHARED",
            "read_file": "LOCAL_ONLY",
            "write_file": "LOCAL_ONLY",
        }
        filtered = AgentSecurityValidator.filter_tools(
            spec, ["echo", "web_search", "read_file", "write_file"], visibilities
        )
        assert filtered == ["echo", "web_search"]

    def test_validate_tool_execution_blocked(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo"],
            ),
        )
        with pytest.raises(AgentSecurityError, match="not in its allowlist"):
            AgentSecurityValidator.validate_tool_execution(spec, "read_file")

    def test_validate_tool_execution_confirmed_blocked(self):
        spec = AgentSpec(
            agent_type="research",
            name="Test",
            objective="Test",
            permissions=AgentPermission(
                tool_allowlist=["echo"],
                can_confirm_actions=False,
            ),
        )
        with pytest.raises(AgentSecurityError, match="cannot set confirmed=True"):
            AgentSecurityValidator.validate_tool_execution(spec, "echo", confirmed=True)


class TestAgentFactory:
    """AgentFactory creation and validation tests."""

    def test_create_custom_agent(self):
        factory = AgentFactory()
        agent = factory.create_agent(
            agent_type="custom",
            name="Test Agent",
            objective="Test objective",
            tool_allowlist=["echo"],
        )
        assert agent.spec.agent_type == "custom"
        assert agent.spec.name == "Test Agent"
        assert "echo" in agent.spec.permissions.tool_allowlist

    def test_create_research_agent(self):
        factory = AgentFactory()
        agent = factory.create_research_agent(
            name="Researcher",
            objective="Research testing frameworks",
        )
        assert agent.spec.agent_type == "research"
        assert "web_search" in agent.spec.permissions.tool_allowlist
        assert "read_file" not in agent.spec.permissions.tool_allowlist

    def test_create_developer_agent(self):
        factory = AgentFactory()
        agent = factory.create_developer_agent(
            name="Developer",
            objective="Write code",
        )
        assert agent.spec.agent_type == "developer"
        assert "read_file" in agent.spec.permissions.tool_allowlist
        assert "write_file" in agent.spec.permissions.tool_allowlist
        assert agent.spec.permissions.can_access_local_only_tools is True

    def test_create_analyst_agent(self):
        factory = AgentFactory()
        agent = factory.create_analyst_agent(
            name="Analyst",
            objective="Analyze metrics",
        )
        assert agent.spec.agent_type == "analyst"
        assert "get_system_metrics" in agent.spec.permissions.tool_allowlist

    def test_create_critic_agent(self):
        factory = AgentFactory()
        agent = factory.create_critic_agent(
            name="Critic",
            objective="Review code",
        )
        assert agent.spec.agent_type == "critic"
        assert "echo" in agent.spec.permissions.tool_allowlist
        assert agent.spec.permissions.max_iterations == 5

    def test_invalid_agent_type(self):
        factory = AgentFactory()
        with pytest.raises(AgentValidationError, match="Invalid agent_type"):
            factory.create_agent(
                agent_type="invalid",
                name="Bad Agent",
                objective="Test",
            )

    def test_invalid_tool_name(self):
        factory = AgentFactory()
        with pytest.raises(AgentValidationError, match="invalid tool name"):
            factory.create_agent(
                agent_type="custom",
                name="Bad Agent",
                objective="Test",
                tool_allowlist=["echo", "invalid tool name!"],
            )

    def test_agent_registry(self):
        registry = AgentRegistry()
        factory = AgentFactory(registry=registry)

        agent = factory.create_agent(
            agent_type="custom",
            name="Test Agent",
            objective="Test",
            tool_allowlist=["echo"],
        )

        assert registry.get(agent.agent_id) is agent
        assert registry.total_count == 1
        assert registry.active_count == 1

        registry.unregister(agent.agent_id)
        assert registry.total_count == 0
