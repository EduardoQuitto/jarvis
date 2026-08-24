"""System event models for the event bus."""

from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """All system event types."""
    # Task events
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

    # Goal events
    GOAL_CREATED = "GOAL_CREATED"
    GOAL_STARTED = "GOAL_STARTED"
    GOAL_COMPLETED = "GOAL_COMPLETED"
    GOAL_FAILED = "GOAL_FAILED"
    GOAL_CANCELLED = "GOAL_CANCELLED"

    # Plan events
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_STEP_STARTED = "PLAN_STEP_STARTED"
    PLAN_STEP_COMPLETED = "PLAN_STEP_COMPLETED"
    PLAN_STEP_FAILED = "PLAN_STEP_FAILED"

    # Agent events
    AGENT_CREATED = "AGENT_CREATED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"

    # Replan events
    REPLANNING_STARTED = "REPLANNING_STARTED"
    REPLANNING_COMPLETED = "REPLANNING_COMPLETED"

    # System events
    DEVICE_ONLINE = "DEVICE_ONLINE"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    USER_MESSAGE = "USER_MESSAGE"
    ASSISTANT_RESPONSE = "ASSISTANT_RESPONSE"
    PROVIDER_SELECTED = "PROVIDER_SELECTED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    PROVIDER_ONLINE = "PROVIDER_ONLINE"
    PROVIDER_OFFLINE = "PROVIDER_OFFLINE"
    ROUTING_STARTED = "ROUTING_STARTED"


class SystemEvent(BaseModel):
    """A structured event for the JARVIS event system."""
    event_type: EventType
    source: str = Field(default="system", description="Source component")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
