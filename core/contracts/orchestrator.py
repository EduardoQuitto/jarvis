"""Contracts for the Orchestrator — the central brain of JARVIS."""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class OrchestratorMessageType(str, Enum):
    """Types of events the orchestrator can emit."""
    THINKING = "THINKING"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_USER = "WAITING_USER"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    TASK_CREATED = "TASK_CREATED"
    TASK_STATUS = "TASK_STATUS"


class OrchestratorRequest(BaseModel):
    """Input to the orchestrator from a user."""
    message: str = Field(..., description="User's text message")
    session_id: Optional[str] = Field(default=None, description="Conversation session ID (creates new if None)")
    device_id: str = Field(default="unknown", description="Device that sent the message")
    device_capabilities: List[str] = Field(default_factory=list, description="Capabilities of the originating device")
    confirmation_id: Optional[str] = Field(default=None, description="ID of the action being confirmed/denied")
    approved: Optional[bool] = Field(default=None, description="Whether the confirmation was approved (None = pending)")


class OrchestratorToolCall(BaseModel):
    """A tool call the orchestrator wants to execute."""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str = Field(default="", description="Unique call ID for tracking")


class OrchestratorToolResult(BaseModel):
    """Result of a tool call executed by the orchestrator."""
    tool_name: str
    call_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class OrchestratorStreamEvent(BaseModel):
    """An event emitted during orchestrator processing for streaming to UI."""
    event_type: OrchestratorMessageType
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrchestratorResponse(BaseModel):
    """Complete response from the orchestrator after processing a message."""
    session_id: str = Field(..., description="Conversation session ID")
    response_text: str = Field(default="", description="Text response to show the user")
    tool_calls_made: List[OrchestratorToolResult] = Field(default_factory=list)
    task_created: Optional[str] = Field(default=None, description="Task ID if a task was created")
    needs_confirmation: bool = Field(default=False, description="Whether the response is waiting for user confirmation")
    confirmation_id: Optional[str] = Field(default=None, description="ID for the pending confirmation")
    confirmation_details: Optional[str] = Field(default=None, description="What needs confirmation")
    iterations_used: int = Field(default=0, description="Number of LLM round-trips used")
    error: Optional[str] = Field(default=None, description="Global error if processing failed")
