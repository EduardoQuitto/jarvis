"""Tests for GoalEngine — goal lifecycle, replanning, and integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.goal.engine import GoalEngine
from core.contracts.goal import Goal, GoalResult, GoalStatus, ReplanDecision
from core.contracts.enums import ReplanAction


class TestGoalEngine:
    """GoalEngine lifecycle tests."""

    @pytest.mark.asyncio
    async def test_create_goal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(
            objective="Research Python testing frameworks",
            priority="normal",
            success_criteria=["Find top 3 frameworks", "Compare features"],
        )
        assert goal.goal_id.startswith("goal-")
        assert goal.objective == "Research Python testing frameworks"
        assert goal.status == GoalStatus.PENDING
        assert goal.priority == "normal"
        assert len(goal.success_criteria) == 2

    @pytest.mark.asyncio
    async def test_start_goal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        updated = await engine.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.RUNNING
        assert updated.plan_id == "plan-123"
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_complete_goal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        result = await engine.complete_goal(goal.goal_id, result="Research completed")
        assert result.status == GoalStatus.COMPLETED
        assert result.result == "Research completed"

        updated = await engine.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.COMPLETED
        assert updated.result == "Research completed"
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_goal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        result = await engine.fail_goal(goal.goal_id, error="Tool execution failed")
        assert result.status == GoalStatus.FAILED
        assert result.error == "Tool execution failed"

        updated = await engine.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.FAILED
        assert "Tool execution failed" in updated.errors

    @pytest.mark.asyncio
    async def test_cancel_goal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        result = await engine.cancel_goal(goal.goal_id)
        assert result.status == GoalStatus.CANCELLED

        updated = await engine.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_replan_first_retry(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        decision = await engine.request_replan(goal.goal_id, "step-1", "Tool failed")
        assert decision.action == ReplanAction.RETRY_SAME
        assert goal.retry_count == 1

    @pytest.mark.asyncio
    async def test_replan_skip_after_retries(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        # First retry
        await engine.request_replan(goal.goal_id, "step-1", "Tool failed")
        # Second retry
        decision = await engine.request_replan(goal.goal_id, "step-1", "Tool failed again")
        assert decision.action == ReplanAction.SKIP_STEP
        assert goal.retry_count == 2

    @pytest.mark.asyncio
    async def test_replan_ask_user_after_max(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        # Use up retries
        await engine.request_replan(goal.goal_id, "step-1", "Failed 1")
        await engine.request_replan(goal.goal_id, "step-1", "Failed 2")
        decision = await engine.request_replan(goal.goal_id, "step-1", "Failed 3")
        assert decision.action == ReplanAction.ASK_USER

    @pytest.mark.asyncio
    async def test_replan_abort_when_not_retriable(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        goal.max_retries = 0
        await engine.start_goal(goal.goal_id, plan_id="plan-123")

        decision = await engine.request_replan(goal.goal_id, "step-1", "Failed")
        assert decision.action == ReplanAction.ABORT

    @pytest.mark.asyncio
    async def test_register_unregister_agent(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test objective")
        await engine.register_agent(goal.goal_id, "agent-001")
        await engine.register_agent(goal.goal_id, "agent-002")

        updated = await engine.get_goal(goal.goal_id)
        assert len(updated.active_agent_ids) == 2
        assert "agent-001" in updated.active_agent_ids

        await engine.unregister_agent(goal.goal_id, "agent-001")
        updated = await engine.get_goal(goal.goal_id)
        assert len(updated.active_agent_ids) == 1
        assert "agent-001" not in updated.active_agent_ids

    @pytest.mark.asyncio
    async def test_list_goals(self):
        engine = GoalEngine()
        await engine.create_goal(objective="Goal 1")
        await engine.create_goal(objective="Goal 2")
        g3 = await engine.create_goal(objective="Goal 3")
        await engine.start_goal(g3.goal_id, plan_id="plan-3")

        all_goals = engine.list_goals()
        assert len(all_goals) == 3

        running = engine.list_goals(status=GoalStatus.RUNNING)
        assert len(running) == 1
        assert running[0].goal_id == g3.goal_id

    @pytest.mark.asyncio
    async def test_list_active_goals(self):
        engine = GoalEngine()
        g1 = await engine.create_goal(objective="Goal 1")
        g2 = await engine.create_goal(objective="Goal 2")
        await engine.start_goal(g1.goal_id, plan_id="plan-1")
        await engine.complete_goal(g2.goal_id, result="Done")

        active = engine.list_active_goals()
        assert len(active) == 1
        assert active[0].goal_id == g1.goal_id

    @pytest.mark.asyncio
    async def test_get_goal_not_found(self):
        engine = GoalEngine()
        goal = await engine.get_goal("goal-nonexistent")
        assert goal is None

    @pytest.mark.asyncio
    async def test_complete_goal_not_found(self):
        engine = GoalEngine()
        result = await engine.complete_goal("goal-nonexistent", result="Done")
        assert result.status == GoalStatus.FAILED
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_goal_is_terminal(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test")
        assert not goal.is_terminal()

        await engine.complete_goal(goal.goal_id, result="Done")
        goal = await engine.get_goal(goal.goal_id)
        assert goal.is_terminal()

    @pytest.mark.asyncio
    async def test_goal_can_replan(self):
        engine = GoalEngine()
        goal = await engine.create_goal(objective="Test")
        assert goal.can_replan()

        goal.max_retries = 0
        assert not goal.can_replan()
