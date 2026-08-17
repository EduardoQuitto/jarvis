"""Task Plan Executor and State Machine."""

import time
from typing import Dict, Optional
from core.contracts.enums import SecurityLevel, TaskStatus
from core.contracts.planner import ExecutionPlan, PlanResult, TaskStep
from core.contracts.memory import AuditEntry, BaseMemoryProvider
from core.config import get_settings
from tools.registry import ToolRegistry, get_tool_registry


class PlanExecutor:
    """Orchestrates step-by-step plan execution with policy checks and state transitions."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        memory_provider: Optional[BaseMemoryProvider] = None,
    ):
        self.registry = tool_registry or get_tool_registry()
        self.memory = memory_provider

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        confirmed_steps: Optional[Dict[str, bool]] = None,
    ) -> PlanResult:
        """Execute all steps in an ExecutionPlan sequentially until completion or required confirmation."""
        confirmed_steps = confirmed_steps or {}
        settings = get_settings()
        start_time = time.perf_counter()
        step_results = {}
        executed_count = 0

        plan.status = TaskStatus.RUNNING

        for idx in range(plan.current_step_index, len(plan.steps)):
            step = plan.steps[idx]
            plan.current_step_index = idx

            # Check dependencies
            for dep_id in step.depends_on:
                dep_res = step_results.get(dep_id)
                if not dep_res or not dep_res.success:
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
                        error=f"Dependency '{dep_id}' for step '{step.step_id}' failed or was not executed.",
                    )

            # Determine confirmation flag for this step
            is_confirmed = confirmed_steps.get(step.step_id, False)

            # Execute tool
            step.status = TaskStatus.RUNNING
            result = await self.registry.execute_tool(
                name=step.tool_name,
                parameters=step.parameters,
                confirmed=is_confirmed,
            )

            step.result = result
            step_results[step.step_id] = result
            executed_count += 1

            # Log audit if memory available
            if self.memory:
                try:
                    await self.memory.log_audit(
                        AuditEntry(
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
                if "requires user confirmation" in (result.error or "") or "requires explicit" in (result.error or ""):
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
                    )
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
                        error=f"Step '{step.step_id}' execution failed: {result.error}",
                    )
            else:
                step.status = TaskStatus.COMPLETED

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
