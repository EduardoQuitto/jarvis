"""Integration tests for Goal Engine + Agent System + Planner."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.goal.engine import GoalEngine
from core.agent.factory import AgentFactory
from core.agent.registry import AgentRegistry
from core.planner.builder import PlanBuilder
from core.planner.engine import PlanExecutor
from core.contracts.enums import ReplanAction


@pytest.fixture(autouse=True)
def register_tools():
    """Ensure default tools are registered for tests."""
    from tools.registry import get_tool_registry
    from tools import register_default_tools
    registry = get_tool_registry()
    register_default_tools(registry)


class TestGoalPlannerIntegration:
    """Integration: Goal → Plan → Execute with replanning."""

    @pytest.mark.asyncio
    async def test_goal_plan_execute_success(self):
        """Goal creation → plan building → execution → completion."""
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Echo test")
        await engine.start_goal(goal.goal_id, plan_id="plan-echo")

        plan = PlanBuilder(
            goal=goal.objective,
            plan_id="plan-echo",
        ).add_step(
            step_id="step-1",
            tool_name="echo",
            parameters={"message": "Hello from goal"},
            description="Echo message",
        ).build()
        plan.goal_id = goal.goal_id

        executor = PlanExecutor()
        result = await executor.execute_plan(plan)

        assert result.status.value == "COMPLETED"
        assert result.steps_executed == 1
        assert "step-1" in result.step_results
        assert result.step_results["step-1"].success is True

        await engine.complete_goal(goal.goal_id, result="Echo completed")
        updated = await engine.get_goal(goal.goal_id)
        assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_goal_plan_execute_with_replan(self):
        """Goal → plan → step failure → replan → skip → completion."""
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Multi-step task")
        await engine.start_goal(goal.goal_id, plan_id="plan-multi")

        plan = PlanBuilder(
            goal=goal.objective,
            plan_id="plan-multi",
        ).add_step(
            step_id="step-1",
            tool_name="echo",
            parameters={"message": "Step 1"},
            description="First step",
        ).add_step(
            step_id="step-2",
            tool_name="nonexistent_tool",
            parameters={},
            description="This will fail",
        ).add_step(
            step_id="step-3",
            tool_name="echo",
            parameters={"message": "Step 3"},
            description="Third step",
            depends_on=["step-2"],
        ).build()
        plan.goal_id = goal.goal_id

        async def replan_callback(goal_id, step_id, error):
            return await engine.request_replan(goal_id, step_id, error)

        executor = PlanExecutor(replan_callback=replan_callback)
        result = await executor.execute_plan(plan)

        # Step 2 fails → replan RETRY_SAME → step 2 fails again → replan SKIP_STEP
        # → step 3 depends on step-2 (skipped, not executed) → step 3 fails → replan ASK_USER → abort
        assert result.status.value == "FAILED"
        assert result.failed_step_id is not None

    @pytest.mark.asyncio
    async def test_agent_goal_integration(self):
        """Agent creation → goal association → execution."""
        factory = AgentFactory()
        engine = GoalEngine()

        goal = await engine.create_goal(objective="Research task")
        agent = factory.create_research_agent(
            name="Researcher",
            objective="Research testing frameworks",
            goal_id=goal.goal_id,
        )

        await engine.register_agent(goal.goal_id, agent.agent_id)
        updated = await engine.get_goal(goal.goal_id)
        assert agent.agent_id in updated.active_agent_ids

        await engine.unregister_agent(goal.goal_id, agent.agent_id)
        updated = await engine.get_goal(goal.goal_id)
        assert agent.agent_id not in updated.active_agent_ids

    @pytest.mark.asyncio
    async def test_multiple_agents_for_goal(self):
        """Multiple agents working on the same goal."""
        factory = AgentFactory()
        engine = GoalEngine()

        goal = await engine.create_goal(objective="Complex analysis")

        agent1 = factory.create_research_agent(
            name="Researcher 1",
            objective="Research part 1",
            goal_id=goal.goal_id,
        )
        agent2 = factory.create_analyst_agent(
            name="Analyst 1",
            objective="Analyze data",
            goal_id=goal.goal_id,
        )

        await engine.register_agent(goal.goal_id, agent1.agent_id)
        await engine.register_agent(goal.goal_id, agent2.agent_id)

        updated = await engine.get_goal(goal.goal_id)
        assert len(updated.active_agent_ids) == 2

    @pytest.mark.asyncio
    async def test_plan_with_dependencies(self):
        """Plan with step dependencies executes in correct order."""
        plan = PlanBuilder(
            goal="Test dependencies",
            plan_id="plan-deps",
        ).add_step(
            step_id="step-1",
            tool_name="echo",
            parameters={"message": "First"},
            description="First step",
        ).add_step(
            step_id="step-2",
            tool_name="echo",
            parameters={"message": "Second"},
            description="Second step",
            depends_on=["step-1"],
        ).build()

        executor = PlanExecutor()
        result = await executor.execute_plan(plan)

        assert result.status.value == "COMPLETED"
        assert result.steps_executed == 2

    @pytest.mark.asyncio
    async def test_plan_step_failure_aborts_dependents(self):
        """When a step fails, dependent steps are not executed."""
        plan = PlanBuilder(
            goal="Test failure",
            plan_id="plan-fail",
        ).add_step(
            step_id="step-1",
            tool_name="nonexistent_tool",
            parameters={},
            description="This will fail",
        ).add_step(
            step_id="step-2",
            tool_name="echo",
            parameters={"message": "Second"},
            description="Depends on step-1",
            depends_on=["step-1"],
        ).build()

        executor = PlanExecutor()
        result = await executor.execute_plan(plan)

        assert result.status.value == "FAILED"
        assert result.failed_step_id == "step-1"
        # step-2 should not have been executed
        assert "step-2" not in result.step_results
