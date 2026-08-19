"""Contracts for Task management and lifecycle."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.contracts.enums import TaskStatus


class TaskPriority(str):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Task(BaseModel):
    """Persistent task representing a user goal."""
    task_id: str = Field(..., description="Unique task identifier")
    objective: str = Field(..., description="What the user wants to achieve")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context for the task")
    priority: str = Field(default="normal", description="Task priority: low, normal, high, urgent")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    plan_id: Optional[str] = Field(default=None, description="Associated ExecutionPlan ID if any")
    conversation_id: Optional[str] = Field(default=None, description="Originating conversation ID")
    device_id: Optional[str] = Field(default=None, description="Device that created the task")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    current_step: Optional[str] = Field(default=None, description="Current step ID being executed")
    progress_pct: float = Field(default=0.0, description="Completion percentage 0-100")
    total_steps: int = Field(default=0, description="Total steps in the plan")
    completed_steps: int = Field(default=0, description="Steps completed so far")

    result: Optional[str] = Field(default=None, description="Final result or summary")
    errors: List[str] = Field(default_factory=list, description="Accumulated error messages")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    max_retries: int = Field(default=2, description="Maximum allowed retries")
    waiting_reason: Optional[str] = Field(default=None, description="Why the task is waiting")


class TaskCheckpoint(BaseModel):
    """Snapshot of task progress at a specific step."""
    id: Optional[int] = Field(None)
    task_id: str = Field(..., description="Parent task ID")
    step_id: str = Field(..., description="Plan step ID")
    step_description: str = Field(default="")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    result_json: Optional[str] = Field(default=None, description="Serialized tool result")
    error: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskCreateRequest(BaseModel):
    """Request to create a new task."""
    objective: str = Field(..., description="What to achieve")
    context: Dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="normal")
    conversation_id: Optional[str] = None
    device_id: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    """Request to update a task."""
    status: Optional[TaskStatus] = None
    result: Optional[str] = None
    waiting_reason: Optional[str] = None
