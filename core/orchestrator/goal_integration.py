"""Orchestrator Goal Integration — routes complex requests to the GoalEngine.

This module adds goal-oriented processing to the Orchestrator while
preserving backward compatibility for simple requests.
"""

from typing import Any, Dict, List, Optional

from core.contracts.orchestrator import OrchestratorRequest, OrchestratorResponse
from core.contracts.goal import Goal, GoalStatus
from core.goal.engine import GoalEngine, get_goal_engine
from core.agent.factory import AgentFactory, get_agent_factory
from core.agent.registry import get_agent_registry
from core.planner.builder import PlanBuilder
from core.planner.engine import PlanExecutor
from core.contracts.planner import ExecutionPlan, ReplanDecision
from core.contracts.enums import ReplanAction
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.orchestrator_goal")


# Keywords that indicate a complex, goal-oriented request
COMPLEXITY_INDICATORS = [
    "research and",
    "analyze and",
    "create a plan",
    "decompose",
    "step by step",
    "multi-step",
    "first.*then",
    "investigate",
    "compare",
    "evaluate",
    "design",
    "implement",
    "build",
    "develop",
]


def is_complex_request(message: str) -> bool:
    """Heuristic to determine if a request is complex enough for the GoalEngine.

    Simple requests (single tool calls, quick questions) go through the
    normal Orchestrator flow. Complex requests (multi-step, research,
    analysis) are routed to the GoalEngine.
    """
    msg_lower = message.lower()

    # Check for complexity indicators
    for indicator in COMPLEXITY_INDICATORS:
        if indicator in msg_lower:
            return True

    # Check for length (longer messages tend to be more complex)
    if len(message) > 200:
        return True

    # Check for multiple action verbs
    action_verbs = ["create", "analyze", "research", "compare", "evaluate", "design", "implement", "build"]
    verb_count = sum(1 for v in action_verbs if v in msg_lower)
    if verb_count >= 2:
        return True

    return False


class GoalOrchestrator:
    """Extended Orchestrator that can route to GoalEngine for complex requests.

    This wraps the existing Orchestrator and adds:
    1. Complexity detection
    2. Goal creation
    3. Agent creation and management
    4. Plan execution with replanning
    5. Result aggregation

    Simple requests still go through the normal Orchestrator flow.
    """

    def __init__(self, orchestrator, goal_engine: Optional[GoalEngine] = None):
        self._orchestrator = orchestrator
        self._goal_engine = goal_engine or get_goal_engine()
        self._agent_factory = get_agent_factory()
        self._agent_registry = get_agent_registry()
        self._event_bus = get_event_bus()

    async def process_message(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """Process a user message, routing to GoalEngine if complex.

        Flow:
        1. If confirmation_id → handle confirmation (always via Orchestrator)
        2. If simple request → Orchestrator processes directly
        3. If complex request → GoalEngine manages the goal
        """
        # Always handle confirmations via the normal Orchestrator
        if request.confirmation_id:
            return await self._orchestrator.process_message(request)

        # Check if this is a complex request
        if not is_complex_request(request.message):
            # Simple request — use normal Orchestrator
            return await self._orchestrator.process_message(request)

        # Complex request — route to GoalEngine
        logger.info("Routing complex request to GoalEngine: %s", request.message[:80])

        try:
            return await self._handle_complex_request(request)
        except Exception as e:
            logger.error("GoalEngine error: %s", str(e))
            # Fallback to normal Orchestrator
            return await self._orchestrator.process_message(request)

    async def _handle_complex_request(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """Handle a complex request via GoalEngine."""
        # Create a goal
        goal = await self._goal_engine.create_goal(
            objective=request.message,
            context={"device_id": request.device_id},
            priority="normal",
            conversation_id=request.session_id,
            device_id=request.device_id,
        )

        # Create a plan (simplified — in real usage, LLM would decompose)
        plan = PlanBuilder(
            goal=goal.objective,
            plan_id=f"plan-{goal.goal_id}",
        ).add_step(
            step_id="step-1",
            tool_name="echo",
            parameters={"message": f"Processing: {goal.objective}"},
            description="Acknowledge the request",
        ).build()
        plan.goal_id = goal.goal_id

        # Start the goal
        await self._goal_engine.start_goal(goal.goal_id, plan.plan_id)

        # Create an agent for this goal
        agent = self._agent_factory.create_agent(
            agent_type="custom",
            name=f"Goal Agent: {goal.objective[:30]}",
            objective=goal.objective,
            context=goal.context,
            tool_allowlist=["echo", "get_current_time"],
            goal_id=goal.goal_id,
        )

        # Register agent with goal
        await self._goal_engine.register_agent(goal.goal_id, agent.agent_id)

        # Execute the plan with replanning
        executor = PlanExecutor(
            replan_callback=self._goal_engine.request_replan,
        )

        plan_result = await executor.execute_plan(plan)

        # Complete or fail the goal based on result
        if plan_result.status.value == "COMPLETED":
            result = await self._goal_engine.complete_goal(
                goal.goal_id,
                result=plan_result.step_results.get("step-1", type("", (), {"data": {}})()).data.get("message", "Completed") if plan_result.step_results else "Completed",
            )
        else:
            result = await self._goal_engine.fail_goal(
                goal.goal_id,
                error=plan_result.error or "Plan execution failed",
            )

        # Build response
        response_text = result.result or result.error or "Goal processing completed."

        return OrchestratorResponse(
            session_id=request.session_id or f"goal-{goal.goal_id}",
            response_text=response_text,
            task_created=goal.goal_id,
            iterations_used=1,
        )
