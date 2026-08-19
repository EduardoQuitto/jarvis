"""System event models for the event bus."""

from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """All system event types."""
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    STEP_COMPLETED = "STEP_COMPLETED"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_USER = "WAITING_USER"
    DEVICE_ONLINE = "DEVICE_ONLINE"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    USER_MESSAGE = "USER_MESSAGE"
    ASSISTANT_RESPONSE = "ASSISTANT_RESPONSE"


class SystemEvent(BaseModel):
    """A structured event for the JARVIS event system."""
    event_type: EventType
    source: str = Field(default="system", description="Source component")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
