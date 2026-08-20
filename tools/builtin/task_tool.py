"""Create and manage tasks through the LLM."""

import json
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult


class CreateTaskArgs(BaseModel):
    objective: str = Field(..., description="Clear description of what the task should accomplish")
    priority: str = Field(default="normal", description="Task priority: low, normal, high, urgent")
    context: Optional[str] = Field(default=None, description="Additional context as JSON string")


class CreateTaskTool(BaseTool):
    """Create a new background task for complex multi-step operations.

    Use this when the user's request is complex and requires multiple steps,
    or when the task will take a long time to complete.
    The system will plan and execute the task, then report results.
    """

    name: str = "create_task"
    description: str = (
        "Create a new background task for complex multi-step operations. "
        "Use when the request requires planning, multiple steps, or long execution. "
        "The task will be planned and executed automatically."
    )
    security_level: SecurityLevel = SecurityLevel.YELLOW
    args_schema: Optional[Type[BaseModel]] = CreateTaskArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        objective = kwargs.get("objective", "")
        priority = kwargs.get("priority", "normal")
        context_str = kwargs.get("context")

        if not objective:
            return ToolResult.fail(
                error="Objective is required to create a task.",
                security_level=self.security_level,
            )

        context = {}
        if context_str:
            try:
                context = json.loads(context_str)
            except json.JSONDecodeError:
                context = {"raw": context_str}

        from core.task.manager import TaskManager
        manager = TaskManager()
        task = await manager.create_task(
            objective=objective,
            context=context,
            priority=priority,
        )

        return ToolResult.ok(
            data={
                "task_id": task.task_id,
                "objective": task.objective,
                "status": task.status.value,
                "priority": task.priority,
            },
            security_level=self.security_level,
        )
