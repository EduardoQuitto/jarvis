"""Task Manager — persistent task lifecycle, state machine, and recovery."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.contracts.enums import TaskStatus
from core.contracts.task import Task
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger

logger = get_logger("jarvis.task_manager")


class TaskManager:
    """Manages persistent tasks with full lifecycle: create, plan, run, verify, complete/fail."""

    def __init__(self, memory: Optional[SQLiteMemoryProvider] = None):
        self._memory = memory

    def _get_memory(self) -> SQLiteMemoryProvider:
        if self._memory is None:
            self._memory = SQLiteMemoryProvider()
        return self._memory

    async def create_task(
        self,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        conversation_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Task:
        """Create a new task."""
        task_id = f"task-{uuid.uuid4().hex[:10]}"
        mem = self._get_memory()
        await mem.create_task(
            task_id=task_id,
            objective=objective,
            context=json.dumps(context or {}),
            priority=priority,
            conversation_id=conversation_id,
            device_id=device_id,
        )
        logger.info("Created task %s: %s", task_id, objective[:60])

        await get_event_bus().publish(SystemEvent(
            event_type=EventType.TASK_CREATED,
            source="task_manager",
            data={"task_id": task_id, "objective": objective},
        ))

        return Task(
            task_id=task_id,
            objective=objective,
            context=context or {},
            priority=priority,
            status=TaskStatus.PENDING,
            conversation_id=conversation_id,
            device_id=device_id,
        )

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        mem = self._get_memory()
        row = await mem.get_task(task_id)
        if not row:
            return None
        return self._row_to_task(row)

    async def update_task(self, task_id: str, **fields) -> None:
        """Update task fields."""
        mem = self._get_memory()
        # Serialize complex fields
        if "context" in fields and isinstance(fields["context"], dict):
            fields["context"] = json.dumps(fields["context"])
        if "errors" in fields and isinstance(fields["errors"], list):
            fields["errors"] = json.dumps(fields["errors"])
        if "status" in fields and hasattr(fields["status"], "value"):
            fields["status"] = fields["status"].value
        await mem.update_task(task_id, **fields)

    async def start_task(self, task_id: str) -> None:
        """Mark a task as running."""
        now = datetime.now(timezone.utc).isoformat()
        await self.update_task(task_id, status=TaskStatus.RUNNING.value, started_at=now)
        await get_event_bus().publish(SystemEvent(
            event_type=EventType.TASK_STARTED,
            source="task_manager",
            data={"task_id": task_id},
        ))

    async def complete_task(self, task_id: str, result: str) -> None:
        """Mark a task as completed."""
        now = datetime.now(timezone.utc).isoformat()
        await self.update_task(
            task_id,
            status=TaskStatus.COMPLETED.value,
            result=result,
            completed_at=now,
            progress_pct=100.0,
        )
        await get_event_bus().publish(SystemEvent(
            event_type=EventType.TASK_COMPLETED,
            source="task_manager",
            data={"task_id": task_id, "result": result[:200]},
        ))

    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        task = await self.get_task(task_id)
        errors = json.loads(task.errors) if task and isinstance(task.errors, str) and task.errors else (task.errors if task else [])
        errors.append(error)
        now = datetime.now(timezone.utc).isoformat()
        await self.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            errors=errors,
            completed_at=now,
        )
        await get_event_bus().publish(SystemEvent(
            event_type=EventType.TASK_FAILED,
            source="task_manager",
            data={"task_id": task_id, "error": error},
        ))

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a task."""
        now = datetime.now(timezone.utc).isoformat()
        await self.update_task(task_id, status=TaskStatus.CANCELLED.value, completed_at=now)
        await get_event_bus().publish(SystemEvent(
            event_type=EventType.TASK_CANCELLED,
            source="task_manager",
            data={"task_id": task_id},
        ))

    async def pause_task(self, task_id: str, reason: str = "User requested pause") -> None:
        """Pause a task."""
        await self.update_task(task_id, status=TaskStatus.PENDING.value, waiting_reason=reason)

    async def resume_task(self, task_id: str) -> None:
        """Resume a paused task."""
        await self.update_task(task_id, status=TaskStatus.RUNNING.value, waiting_reason=None)

    async def list_active_tasks(self) -> List[Task]:
        """List all non-terminal tasks."""
        mem = self._get_memory()
        tasks = []
        for status in ["PENDING", "RUNNING", "WAITING_CONFIRMATION", "PAUSED"]:
            rows = await mem.list_tasks(status=status)
            tasks.extend([self._row_to_task(r) for r in rows])
        return tasks

    async def list_all_tasks(self, limit: int = 50) -> List[Task]:
        """List all tasks."""
        mem = self._get_memory()
        rows = await mem.list_tasks(limit=limit)
        return [self._row_to_task(r) for r in rows]

    async def restore_interrupted_tasks(self) -> List[Task]:
        """Restore tasks that were running/paused before a restart."""
        tasks = await self.list_active_tasks()
        for task in tasks:
            logger.info("Restored interrupted task: %s (%s)", task.task_id, task.status.value)
        return tasks

    def _row_to_task(self, row: Dict[str, Any]) -> Task:
        """Convert a database row to a Task model."""
        return Task(
            task_id=row["task_id"],
            objective=row["objective"],
            context=json.loads(row.get("context", "{}")),
            priority=row.get("priority", "normal"),
            status=TaskStatus(row["status"]),
            plan_id=row.get("plan_id"),
            conversation_id=row.get("conversation_id"),
            device_id=row.get("device_id"),
            current_step=row.get("current_step"),
            progress_pct=float(row.get("progress_pct", 0.0)),
            total_steps=int(row.get("total_steps", 0)),
            completed_steps=int(row.get("completed_steps", 0)),
            result=row.get("result"),
            errors=json.loads(row.get("errors", "[]")),
            retry_count=int(row.get("retry_count", 0)),
            max_retries=int(row.get("max_retries", 2)),
            waiting_reason=row.get("waiting_reason"),
        )
