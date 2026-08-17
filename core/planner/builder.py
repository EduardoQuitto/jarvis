"""Fluent builder for constructing ExecutionPlans."""

import uuid
from typing import Any, Dict, List, Optional
from core.contracts.enums import SecurityLevel, TaskStatus
from core.contracts.planner import ExecutionPlan, TaskStep


class PlanBuilder:
    """Builder pattern to construct structured multi-step ExecutionPlans."""

    def __init__(self, goal: str, plan_id: Optional[str] = None):
        self.goal = goal
        self.plan_id = plan_id or f"plan-{uuid.uuid4().hex[:8]}"
        self.steps: List[TaskStep] = []

    def add_step(
        self,
        step_id: str,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        description: str = "",
        security_level: SecurityLevel = SecurityLevel.GREEN,
        depends_on: Optional[List[str]] = None,
    ) -> "PlanBuilder":
        """Append a new task step to the plan."""
        step = TaskStep(
            step_id=step_id,
            description=description or f"Execute {tool_name}",
            tool_name=tool_name,
            parameters=parameters or {},
            security_level=security_level,
            status=TaskStatus.PENDING,
            depends_on=depends_on or [],
        )
        self.steps.append(step)
        return self

    def build(self) -> ExecutionPlan:
        """Produce the validated ExecutionPlan instance."""
        return ExecutionPlan(
            plan_id=self.plan_id,
            goal=self.goal,
            status=TaskStatus.PENDING,
            steps=self.steps,
            current_step_index=0,
        )
