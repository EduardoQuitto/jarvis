"""Contracts for the Planner and Task Orchestration Engine."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel, TaskStatus, ReplanAction
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
    retry_count: int = Field(default=0, description="Number of retries for this step")
    max_retries: int = Field(default=1, description="Maximum retries allowed for this step")
    replan_action: Optional[ReplanAction] = Field(default=None, description="Action to take if this step fails")


class ExecutionPlan(BaseModel):
    """A multi-step plan decomposed by the Planner."""
    plan_id: str = Field(..., description="Unique identifier for the plan")
    goal_id: Optional[str] = Field(default=None, description="Associated Goal ID")
    goal: str = Field(..., description="High-level goal or user command")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Overall plan status")
    steps: List[TaskStep] = Field(default_factory=list, description="Ordered or dependent sequence of steps")
    current_step_index: int = Field(default=0, description="Pointer to current executing step")
    agent_id: Optional[str] = Field(default=None, description="Agent executing this plan")


class PlanResult(BaseModel):
    """Final outcome of an executed plan."""
    plan_id: str = Field(..., description="Plan ID")
    goal: str = Field(..., description="Original goal")
    status: TaskStatus = Field(..., description="Final plan status")
    steps_executed: int = Field(..., description="Number of steps executed")
    total_duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    step_results: Dict[str, ToolResult] = Field(default_factory=dict, description="Map of step_id to ToolResult")
    error: Optional[str] = Field(None, description="Global failure reason if any")
    failed_step_id: Optional[str] = Field(default=None, description="Step that failed, if any")
    replan_action: Optional[ReplanAction] = Field(default=None, description="Recommended replan action")


class ReplanDecision(BaseModel):
    """Decision made by GoalEngine when a step fails."""
    action: ReplanAction = Field(..., description="ReplanAction to take")
    reason: str = Field(..., description="Why this action was chosen")
    alternative_tool: Optional[str] = Field(default=None, description="Alternative tool if ALTERNATIVE_STEP")
    alternative_params: Optional[Dict[str, Any]] = Field(default=None, description="Alternative parameters")
    skip_step_id: Optional[str] = Field(default=None, description="Step to skip if SKIP_STEP")
