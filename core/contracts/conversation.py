"""Contracts for Conversation management and sessions."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    id: Optional[int] = Field(None, description="Auto-incremented message ID")
    conversation_id: str = Field(..., description="Parent conversation ID")
    role: str = Field(..., description="Message role: system, user, assistant, tool")
    content: str = Field(default="", description="Text content")
    tool_calls_json: Optional[str] = Field(default=None, description="Serialized tool calls JSON")
    tool_call_id: Optional[str] = Field(default=None, description="Tool call ID for tool responses")
    name: Optional[str] = Field(default=None, description="Tool name for tool responses")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSession(BaseModel):
    """A conversation session grouping messages."""
    id: str = Field(..., description="Unique conversation session ID")
    title: Optional[str] = Field(default=None, description="Human-readable session title")
    task_id: Optional[str] = Field(default=None, description="Associated task ID if any")
    device_id: Optional[str] = Field(default=None, description="Device that initiated the conversation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = Field(default=0, description="Number of messages in the session")


class ConversationState(BaseModel):
    """Current state of a conversation for context."""
    session_id: str
    messages: List[ConversationMessage] = Field(default_factory=list)
    active_task_id: Optional[str] = None
    active_task_status: Optional[str] = None
    active_task_progress: Optional[str] = None
