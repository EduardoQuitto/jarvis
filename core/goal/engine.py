"""Goal Engine — manages high-level objectives from user requests."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.contracts.goal import Goal, GoalResult, GoalStatus, ReplanDecision
from core.contracts.enums import ReplanAction
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.task.manager import TaskManager
from core.logger import get_logger

logger = get_logger("jarvis.goal_engine")


class GoalEngine:
    """Manages the lifecycle of high-level goals.

    A Goal is an abstraction over Task that adds:
    - Success criteria
    - Replanning logic
    - Agent tracking
    - Goal-level status transitions

    The GoalEngine does NOT execute tools directly.
    It coordinates with Planner and AgentSystem.
    """

    def __init__(self, task_manager: Optional[TaskManager] = None):
        self._task_manager = task_manager or TaskManager()
        self._goals: Dict[str, Goal] = {}
        self._event_bus = get_event_bus()

    async def create_goal(
        self,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        success_criteria: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Goal:
        """Create a new goal from a user request."""
        goal_id = f"goal-{uuid.uuid4().hex[:8]}"

        goal = Goal(
            goal_id=goal_id,
            objective=objective,
            context=context or {},
            priority=priority,
            status=GoalStatus.PENDING,
            success_criteria=success_criteria or [],
            conversation_id=conversation_id,
            device_id=device_id,
        )

        self._goals[goal_id] = goal

        # Also create a Task for persistence
        task = await self._task_manager.create_task(
            objective=objective,
            context=context,
            priority=priority,
            conversation_id=conversation_id,
            device_id=device_id,
        )
        goal.plan_id = None  # Will be set when plan is created

        logger.info("Created goal %s: %s", goal_id, objective[:60])

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.GOAL_CREATED,
            source="goal_engine",
            data={"goal_id": goal_id, "objective": objective},
        ))

        return goal

    async def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        return self._goals.get(goal_id)

    async def start_goal(self, goal_id: str, plan_id: str) -> None:
        """Mark a goal as running with an associated plan."""
        goal = self._goals.get(goal_id)
        if not goal:
            return

        goal.status = GoalStatus.RUNNING
        goal.plan_id = plan_id
        goal.started_at = datetime.now(timezone.utc)
        goal.updated_at = datetime.now(timezone.utc)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.GOAL_STARTED,
            source="goal_engine",
            data={"goal_id": goal_id, "plan_id": plan_id},
        ))

    async def complete_goal(self, goal_id: str, result: str) -> GoalResult:
        """Mark a goal as completed."""
        goal = self._goals.get(goal_id)
        if not goal:
            return GoalResult(goal_id=goal_id, objective="", status=GoalStatus.FAILED, error="Goal not found")

        goal.status = GoalStatus.COMPLETED
        goal.result = result
        goal.completed_at = datetime.now(timezone.utc)
        goal.updated_at = datetime.now(timezone.utc)

        # Update task
        if goal.plan_id:
            await self._task_manager.complete_task(goal.plan_id, result)

        logger.info("Completed goal %s: %s", goal_id, result[:60])

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.GOAL_COMPLETED,
            source="goal_engine",
            data={"goal_id": goal_id, "result": result[:200]},
        ))

        return GoalResult(
            goal_id=goal_id,
            objective=goal.objective,
            status=GoalStatus.COMPLETED,
            plan_id=goal.plan_id,
            agents_used=goal.active_agent_ids,
            result=result,
        )

    async def fail_goal(self, goal_id: str, error: str) -> GoalResult:
        """Mark a goal as failed."""
        goal = self._goals.get(goal_id)
        if not goal:
            return GoalResult(goal_id=goal_id, objective="", status=GoalStatus.FAILED, error="Goal not found")

        goal.status = GoalStatus.FAILED
        goal.errors.append(error)
        goal.completed_at = datetime.now(timezone.utc)
        goal.updated_at = datetime.now(timezone.utc)

        # Update task
        if goal.plan_id:
            await self._task_manager.fail_task(goal.plan_id, error)

        logger.info("Failed goal %s: %s", goal_id, error[:60])

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.GOAL_FAILED,
            source="goal_engine",
            data={"goal_id": goal_id, "error": error},
        ))

        return GoalResult(
            goal_id=goal_id,
            objective=goal.objective,
            status=GoalStatus.FAILED,
            plan_id=goal.plan_id,
            agents_used=goal.active_agent_ids,
            error=error,
        )

    async def cancel_goal(self, goal_id: str) -> GoalResult:
        """Cancel a goal."""
        goal = self._goals.get(goal_id)
        if not goal:
            return GoalResult(goal_id=goal_id, objective="", status=GoalStatus.FAILED, error="Goal not found")

        goal.status = GoalStatus.CANCELLED
        goal.completed_at = datetime.now(timezone.utc)
        goal.updated_at = datetime.now(timezone.utc)

        # Cancel task
        if goal.plan_id:
            await self._task_manager.cancel_task(goal.plan_id)

        logger.info("Cancelled goal %s", goal_id)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.GOAL_CANCELLED,
            source="goal_engine",
            data={"goal_id": goal_id},
        ))

        return GoalResult(
            goal_id=goal_id,
            objective=goal.objective,
            status=GoalStatus.CANCELLED,
            plan_id=goal.plan_id,
            agents_used=goal.active_agent_ids,
        )

    async def request_replan(self, goal_id: str, failed_step_id: str, error: str) -> ReplanDecision:
        """Decide what to do when a step fails.

        Returns a ReplanDecision that the Planner should execute.
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return ReplanDecision(action=ReplanAction.ABORT, reason="Goal not found")

        if not goal.can_replan():
            return ReplanDecision(action=ReplanAction.ABORT, reason="Max retries exceeded")

        goal.retry_count += 1
        goal.status = GoalStatus.REPLANNING
        goal.updated_at = datetime.now(timezone.utc)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.REPLANNING_STARTED,
            source="goal_engine",
            data={"goal_id": goal_id, "failed_step": failed_step_id, "error": error, "retry": goal.retry_count},
        ))

        # Simple replanning strategy for now
        # In the future, this could use LLM to decide
        if goal.retry_count <= 1:
            decision = ReplanDecision(
                action=ReplanAction.RETRY_SAME,
                reason=f"First retry for step {failed_step_id}",
            )
        elif goal.retry_count <= 2:
            decision = ReplanDecision(
                action=ReplanAction.SKIP_STEP,
                reason=f"Skipping failed step {failed_step_id} after {goal.retry_count} retries",
                skip_step_id=failed_step_id,
            )
        else:
            decision = ReplanDecision(
                action=ReplanAction.ASK_USER,
                reason=f"Multiple failures on step {failed_step_id}, requesting user guidance",
            )

        logger.info("Replan decision for goal %s: %s", goal_id, decision.action)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.REPLANNING_COMPLETED,
            source="goal_engine",
            data={"goal_id": goal_id, "action": decision.action, "reason": decision.reason},
        ))

        return decision

    async def register_agent(self, goal_id: str, agent_id: str) -> None:
        """Register an active agent with a goal."""
        goal = self._goals.get(goal_id)
        if goal and agent_id not in goal.active_agent_ids:
            goal.active_agent_ids.append(agent_id)
            goal.updated_at = datetime.now(timezone.utc)

    async def unregister_agent(self, goal_id: str, agent_id: str) -> None:
        """Remove an agent from a goal's active list."""
        goal = self._goals.get(goal_id)
        if goal and agent_id in goal.active_agent_ids:
            goal.active_agent_ids.remove(agent_id)
            goal.updated_at = datetime.now(timezone.utc)

    def list_goals(self, status: Optional[str] = None) -> List[Goal]:
        """List all goals, optionally filtered by status."""
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return goals

    def list_active_goals(self) -> List[Goal]:
        """List all non-terminal goals."""
        return [g for g in self._goals.values() if not g.is_terminal()]


_goal_engine: Optional[GoalEngine] = None


def get_goal_engine() -> GoalEngine:
    """Access the global GoalEngine instance."""
    global _goal_engine
    if _goal_engine is None:
        _goal_engine = GoalEngine()
    return _goal_engine
