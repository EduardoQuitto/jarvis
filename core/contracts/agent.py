"""Contracts for the Agent System — specialized agent representation and lifecycle."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentStatus:
    """Status lifecycle for agents."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentPermission(BaseModel):
    """Permissions granted to an agent. Immutable after creation."""
    tool_allowlist: List[str] = Field(
        default_factory=list,
        description="Tools this agent may use. Empty = none.",
    )
    provider_allowlist: List[str] = Field(
        default_factory=list,
        description="LLM providers this agent may use. Empty = any.",
    )
    max_iterations: int = Field(default=10, description="Max LLM loop iterations")
    max_duration_seconds: float = Field(default=300.0, description="Max execution time")
    can_confirm_actions: bool = Field(default=False, description="Can this agent confirm YELLOW/RED actions?")
    can_access_local_only_tools: bool = Field(default=False, description="Can see LOCAL_ONLY tools?")


class AgentSpec(BaseModel):
    """Specification for creating an agent. Immutable after creation."""
    agent_type: str = Field(..., description="Agent type: research, developer, analyst, critic, custom")
    name: str = Field(..., description="Human-readable agent name")
    objective: str = Field(..., description="What this agent should achieve")
    description: str = Field(default="", description="Detailed description")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    permissions: AgentPermission = Field(default_factory=AgentPermission)
    goal_id: Optional[str] = Field(default=None, description="Parent goal ID")
    task_id: Optional[str] = Field(default=None, description="Parent task ID")
    provider_name: Optional[str] = Field(default=None, description="Preferred provider (None = auto)")


class AgentState(BaseModel):
    """Current state of a running agent."""
    agent_id: str = Field(..., description="Unique agent identifier")
    spec: AgentSpec = Field(..., description="Creation specification")
    status: str = Field(default=AgentStatus.PENDING, description="Current status")
    session_id: Optional[str] = Field(default=None, description="Conversation session for this agent")
    iterations_used: int = Field(default=0, description="LLM iterations consumed")
    tools_called: List[str] = Field(default_factory=list, description="Tool names invoked")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None, description="Failure reason")


class AgentResult(BaseModel):
    """Result produced by an agent upon completion."""
    agent_id: str = Field(..., description="Agent ID")
    agent_type: str = Field(..., description="Agent type")
    status: str = Field(..., description="Final status")
    result: Optional[str] = Field(default=None, description="Agent's output/finding")
    steps_executed: int = Field(default=0, description="Steps executed by this agent")
    tools_used: List[str] = Field(default_factory=list, description="Tools invoked")
    duration_ms: float = Field(default=0.0, description="Execution duration")
    error: Optional[str] = Field(default=None, description="Failure reason if any")
