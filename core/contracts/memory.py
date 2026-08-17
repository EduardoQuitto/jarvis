"""Contracts for memory providers, audit logs, and persistent state."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel


class MemoryEntry(BaseModel):
    """Generic key-value memory record."""
    key: str = Field(..., description="Unique memory key/namespace")
    value: Any = Field(..., description="JSON-serializable value")
    category: str = Field(default="general", description="Category/scope: system, user, cache, preference")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")


class AuditEntry(BaseModel):
    """Audit record logging tool executions and critical system actions."""
    id: Optional[int] = Field(None, description="Auto-incremented ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the action")
    node_id: str = Field(..., description="Node where action took place")
    tool_name: str = Field(..., description="Executed tool name")
    security_level: SecurityLevel = Field(..., description="Security level of the action")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters supplied to the tool")
    success: bool = Field(..., description="Whether action succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: float = Field(default=0.0, description="Duration in ms")


class BaseMemoryProvider(ABC):
    """Abstract interface for persistent memory storage."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage engine (e.g. create tables)."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, category: str = "general") -> None:
        """Store or update a key-value pair."""
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[MemoryEntry]:
        """Retrieve a key-value pair by key."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key-value pair by key."""
        pass

    @abstractmethod
    async def list_by_category(self, category: str) -> List[MemoryEntry]:
        """List all entries under a specific category."""
        pass

    @abstractmethod
    async def log_audit(self, entry: AuditEntry) -> None:
        """Record an audit trail entry for tool executions."""
        pass

    @abstractmethod
    async def get_recent_audits(self, limit: int = 50) -> List[AuditEntry]:
        """Retrieve the most recent audit log entries."""
        pass
