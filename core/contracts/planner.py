"""Contracts for the Planner and Task Orchestration Engine."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel, TaskStatus
from core.contracts.tool import ToolResult


class TaskStep(BaseModel):
    """An individual atomic step within an execution plan."""
    step_id: str = Field(..., description="Unique step identifier within the plan")
    description: str = Field(..., description="Human readable intent of the step")
    tool_name: str = Field(..., description="Target tool to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    security_level: SecurityLevel = Field(default=SecurityLevel.GREEN, description="Inferred or declared security level")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution status of step")
    result: Optional[ToolResult] = Field(None, description="Execution result when finished")
    depends_on: List[str] = Field(default_factory=list, description="Step IDs that must complete before this step")


class ExecutionPlan(BaseModel):
    """A multi-step plan decomposed by the Planner."""
    plan_id: str = Field(..., description="Unique identifier for the plan")
    goal: str = Field(..., description="High-level goal or user command")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Overall plan status")
    steps: List[TaskStep] = Field(default_factory=list, description="Ordered or dependent sequence of steps")
    current_step_index: int = Field(default=0, description="Pointer to current executing step")


class PlanResult(BaseModel):
    """Final outcome of an executed plan."""
    plan_id: str = Field(..., description="Plan ID")
    goal: str = Field(..., description="Original goal")
    status: TaskStatus = Field(..., description="Final plan status")
    steps_executed: int = Field(..., description="Number of steps executed")
    total_duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    step_results: Dict[str, ToolResult] = Field(default_factory=dict, description="Map of step_id to ToolResult")
    error: Optional[str] = Field(None, description="Global failure reason if any")
