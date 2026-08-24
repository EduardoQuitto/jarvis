"""Contracts for the Goal Engine — high-level objective representation and lifecycle."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.contracts.enums import TaskStatus


class GoalStatus:
    """Status lifecycle for goals."""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    BLOCKED = "blocked"
    FAILED = "failed"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReplanAction:
    """Actions the GoalEngine can take when a step fails."""
    RETRY_SAME = "retry_same"
    SKIP_STEP = "skip_step"
    ALTERNATIVE_STEP = "alternative_step"
    ABORT = "abort"
    ASK_USER = "ask_user"


class Goal(BaseModel):
    """High-level objective received from the user."""
    goal_id: str = Field(..., description="Unique goal identifier")
    objective: str = Field(..., description="What the user wants to achieve")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    priority: str = Field(default="normal", description="Priority: low, normal, high, urgent")
    status: str = Field(default=GoalStatus.PENDING, description="Current goal status")
    conversation_id: Optional[str] = Field(default=None, description="Originating conversation")
    device_id: Optional[str] = Field(default=None, description="Device that created the goal")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    plan_id: Optional[str] = Field(default=None, description="Associated ExecutionPlan ID")
    active_agent_ids: List[str] = Field(default_factory=list, description="Currently active agents")

    success_criteria: List[str] = Field(default_factory=list, description="Conditions for success")
    result: Optional[str] = Field(default=None, description="Final result or summary")
    errors: List[str] = Field(default_factory=list, description="Accumulated errors")
    retry_count: int = Field(default=0, description="Number of replanning attempts")
    max_retries: int = Field(default=3, description="Maximum allowed replanning attempts")

    def is_terminal(self) -> bool:
        return self.status in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED)

    def can_replan(self) -> bool:
        return self.retry_count < self.max_retries and self.status != GoalStatus.CANCELLED


class GoalResult(BaseModel):
    """Final outcome of a goal execution."""
    goal_id: str = Field(..., description="Goal ID")
    objective: str = Field(..., description="Original objective")
    status: str = Field(..., description="Final status")
    plan_id: Optional[str] = Field(default=None, description="Plan used")
    agents_used: List[str] = Field(default_factory=list, description="Agent IDs used")
    steps_executed: int = Field(default=0, description="Total steps executed")
    total_duration_ms: float = Field(default=0.0, description="Total duration")
    result: Optional[str] = Field(default=None, description="Final result")
    error: Optional[str] = Field(default=None, description="Failure reason if any")
    replan_count: int = Field(default=0, description="Number of replanning events")


class ReplanDecision(BaseModel):
    """Decision made by GoalEngine when a step fails."""
    action: str = Field(..., description="ReplanAction to take")
    reason: str = Field(..., description="Why this action was chosen")
    alternative_tool: Optional[str] = Field(default=None, description="Alternative tool if ALTERNATIVE_STEP")
    alternative_params: Optional[Dict[str, Any]] = Field(default=None, description="Alternative parameters")
    skip_step_id: Optional[str] = Field(default=None, description="Step to skip if SKIP_STEP")
