"""Task Plan Executor and State Machine — evolved with replanning support.

Security: PlanExecutor NEVER pre-confirms steps. All tool executions pass
through PolicyEngine with source="plan_executor" and confirmed=False.
When a step requires confirmation, the plan pauses with REQUIRE_APPROVAL.
"""

import time
from typing import Dict, Optional, Callable, Awaitable

from core.contracts.enums import SecurityLevel, TaskStatus, ReplanAction
from core.contracts.planner import ExecutionPlan, PlanResult, TaskStep, ReplanDecision
from core.contracts.memory import AuditEntry, BaseMemoryProvider
from core.config import get_settings
from tools.registry import ToolRegistry, get_tool_registry
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.plan_executor")

# Source identifier for policy enforcement
SOURCE = "plan_executor"


class PlanExecutor:
    """Orchestrates step-by-step plan execution with policy checks, state transitions, and replanning.

    Security model:
    - All tool executions pass through ToolRegistry.execute_tool() with source="plan_executor"
    - confirmed=True is NEVER used (PolicyEngine ignores it for untrusted sources)
    - When a step requires confirmation (YELLOW/RED), plan pauses with REQUIRE_APPROVAL
    - Replanning respects the same security boundaries
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        memory_provider: Optional[BaseMemoryProvider] = None,
        replan_callback: Optional[Callable[[str, str, str], Awaitable[ReplanDecision]]] = None,
    ):
        self.registry = tool_registry or get_tool_registry()
        self.memory = memory_provider
        self.replan_callback = replan_callback
        self._event_bus = get_event_bus()

    async def execute_plan(
        self,
        plan: ExecutionPlan,
    ) -> PlanResult:
        """Execute all steps in an ExecutionPlan with replanning support.

        Security: No pre-confirmation. All steps go through PolicyEngine
        with source="plan_executor" and confirmed=False.

        If a step requires confirmation, the plan pauses with REQUIRE_APPROVAL.
        """
        settings = get_settings()
        start_time = time.perf_counter()
        step_results = {}
        executed_count = 0

        plan.status = TaskStatus.RUNNING

        idx = plan.current_step_index
        while idx < len(plan.steps):
            step = plan.steps[idx]
            plan.current_step_index = idx

            # Check dependencies
            deps_ok = True
            failed_dep = None
            for dep_id in step.depends_on:
                dep_res = step_results.get(dep_id)
                if not dep_res or not dep_res.success:
                    deps_ok = False
                    failed_dep = dep_id
                    break

            if not deps_ok:
                # Dependency failed — try replanning
                if self.replan_callback:
                    decision = await self.replan_callback(
                        plan.goal_id or plan.plan_id,
                        step.step_id,
                        f"Dependency '{failed_dep}' failed",
                    )
                    action_result = await self._handle_replan(plan, step, decision, step_results)
                    if action_result == "continue":
                        continue
                    elif action_result == "skip":
                        idx += 1
                        continue
                    elif action_result == "abort":
                        break
                else:
                    step.status = TaskStatus.FAILED
                    plan.status = TaskStatus.FAILED
                    total_dur = (time.perf_counter() - start_time) * 1000.0
                    return PlanResult(
                        plan_id=plan.plan_id,
                        goal=plan.goal,
                        status=TaskStatus.FAILED,
                        steps_executed=executed_count,
                        total_duration_ms=total_dur,
                        step_results=step_results,
                        error=f"Dependency '{failed_dep}' for step '{step.step_id}' failed.",
                        failed_step_id=step.step_id,
                    )

            # Execute tool — ALWAYS with confirmed=False (no pre-confirmation)
            step.status = TaskStatus.RUNNING

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.PLAN_STEP_STARTED,
                source="plan_executor",
                data={"plan_id": plan.plan_id, "step_id": step.step_id, "tool_name": step.tool_name},
            ))

            result = await self.registry.execute_tool(
                name=step.tool_name,
                parameters=step.parameters,
                confirmed=False,  # NEVER pre-confirm
                source=SOURCE,
            )

            step.result = result
            step_results[step.step_id] = result
            executed_count += 1

            # Log audit if memory available
            if self.memory:
                try:
                    await self.memory.log_audit(
                        AuditEntry(
                            id=None,
                            node_id=settings.node_id,
                            tool_name=step.tool_name,
                            security_level=step.security_level,
                            parameters=step.parameters,
                            success=result.success,
                            error=result.error,
                            duration_ms=result.execution_time_ms,
                        )
                    )
                except Exception:
                    pass

            # Check result outcome
            if not result.success:
                error_msg = result.error or "Unknown error"

                # Check if it's a confirmation requirement
                if ("requires user confirmation" in error_msg
                    or "requires explicit" in error_msg
                    or "cannot confirm actions" in error_msg
                    or "Confirmation required" in error_msg):
                    step.status = TaskStatus.REQUIRE_APPROVAL
                    plan.status = TaskStatus.REQUIRE_APPROVAL
                    total_dur = (time.perf_counter() - start_time) * 1000.0
                    return PlanResult(
                        plan_id=plan.plan_id,
                        goal=plan.goal,
                        status=TaskStatus.REQUIRE_APPROVAL,
                        steps_executed=executed_count,
                        total_duration_ms=total_dur,
                        step_results=step_results,
                        error=f"Step '{step.step_id}' requires explicit user confirmation.",
                        failed_step_id=step.step_id,
                    )

                # Step failed — try replanning
                if self.replan_callback and step.retry_count < step.max_retries:
                    step.retry_count += 1
                    decision = await self.replan_callback(
                        plan.goal_id or plan.plan_id,
                        step.step_id,
                        error_msg,
                    )

                    await self._event_bus.publish(SystemEvent(
                        event_type=EventType.REPLANNING_STARTED,
                        source="plan_executor",
                        data={
                            "plan_id": plan.plan_id,
                            "step_id": step.step_id,
                            "action": decision.action,
                            "reason": decision.reason,
                        },
                    ))

                    action_result = await self._handle_replan(plan, step, decision, step_results)

                    if action_result == "continue":
                        continue  # Retry same step
                    elif action_result == "skip":
                        idx += 1
                        continue
                    elif action_result == "abort":
                        break

                # No replanning or max retries exceeded
                step.status = TaskStatus.FAILED
                plan.status = TaskStatus.FAILED
                total_dur = (time.perf_counter() - start_time) * 1000.0
                return PlanResult(
                    plan_id=plan.plan_id,
                    goal=plan.goal,
                    status=TaskStatus.FAILED,
                    steps_executed=executed_count,
                    total_duration_ms=total_dur,
                    step_results=step_results,
                    error=f"Step '{step.step_id}' execution failed: {error_msg}",
                    failed_step_id=step.step_id,
                )

            # Step succeeded
            step.status = TaskStatus.COMPLETED

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.PLAN_STEP_COMPLETED,
                source="plan_executor",
                data={"plan_id": plan.plan_id, "step_id": step.step_id, "success": True},
            ))

            idx += 1

        plan.status = TaskStatus.COMPLETED
        total_dur = (time.perf_counter() - start_time) * 1000.0
        return PlanResult(
            plan_id=plan.plan_id,
            goal=plan.goal,
            status=TaskStatus.COMPLETED,
            steps_executed=executed_count,
            total_duration_ms=total_dur,
            step_results=step_results,
            error=None,
        )

    async def _handle_replan(
        self,
        plan: ExecutionPlan,
        step: TaskStep,
        decision: ReplanDecision,
        step_results: Dict,
    ) -> str:
        """Handle a replan decision. Returns: 'continue', 'skip', or 'abort'."""
        if decision.action == ReplanAction.RETRY_SAME:
            return "continue"

        elif decision.action == ReplanAction.SKIP_STEP:
            return "skip"

        elif decision.action == ReplanAction.ALTERNATIVE_STEP:
            # Replace the step's tool with the alternative
            if decision.alternative_tool:
                step.tool_name = decision.alternative_tool
                step.parameters = decision.alternative_params or step.parameters
                step.retry_count = 0  # Reset retry count for new tool
                return "continue"

        elif decision.action == ReplanAction.ABORT:
            plan.status = TaskStatus.FAILED
            return "abort"

        elif decision.action == ReplanAction.ASK_USER:
            plan.status = TaskStatus.REQUIRE_APPROVAL
            return "abort"

        return "abort"
