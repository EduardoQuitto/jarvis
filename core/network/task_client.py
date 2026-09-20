"""Distributed task lifecycle bridge (CORE intelligence, SERVER persistence).

Thin layer over RemoteNodeClient that speaks the SERVER task API and
converts payloads to Task contracts. It never executes tasks locally,
never duplicates TaskManager, and never invents task state: the SERVER
SQLite store remains the single source of truth.

Only RemoteNodeError is raised (standardized transport errors). A missing
task (HTTP 404) yields None from get_task() instead of raising.

This is lifecycle administration only — no worker, no scheduler, no queue,
no polling, no autonomous execution on either side.
"""

from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.contracts.enums import TaskStatus
from core.contracts.task import Task
from core.logger import get_logger
from core.network.node_client import RemoteNodeClient, RemoteNodeError

logger = get_logger("jarvis.network.task_client")

CORE_DEVICE_ID = "jarvis-core"


def _coerce_status(value: Any) -> TaskStatus:
    try:
        return TaskStatus(value)
    except (ValueError, TypeError):
        return TaskStatus.PENDING


def dict_to_task(data: Dict[str, Any]) -> Task:
    """Convert a SERVER task payload to a Task contract (missing fields default)."""
    errors = data.get("errors")
    return Task(
        task_id=str(data.get("task_id", "")),
        objective=str(data.get("objective", "")),
        context=data.get("context") if isinstance(data.get("context"), dict) else {},
        priority=str(data.get("priority", "normal")),
        status=_coerce_status(data.get("status")),
        conversation_id=data.get("conversation_id"),
        device_id=data.get("device_id"),
        progress_pct=float(data.get("progress_pct") or 0.0),
        result=data.get("result"),
        errors=list(errors) if isinstance(errors, list) else [],
    )


class DistributedTaskClient:
    """Administers SERVER-persisted tasks from the CORE over the network."""

    def __init__(self, client: RemoteNodeClient, device_id: str = CORE_DEVICE_ID):
        self._client = client
        self._device_id = device_id

    @classmethod
    def from_settings(cls, settings=None, client: Optional[RemoteNodeClient] = None) -> Optional["DistributedTaskClient"]:
        """Build from settings, or None when no SERVER URL is configured."""
        settings = settings or get_settings()
        if not settings.server_url:
            return None
        return cls(
            client=client or RemoteNodeClient(
                base_url=settings.server_url,
                api_key=settings.server_api_key,
                timeout=settings.server_timeout,
            ),
            device_id=settings.node_id or CORE_DEVICE_ID,
        )

    async def create_task(
        self,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        conversation_id: Optional[str] = None,
    ) -> Task:
        """Create a task persisted on the SERVER, attributed to this Core."""
        created = await self._client.create_task(
            objective=objective,
            context=context,
            priority=priority,
            conversation_id=conversation_id,
            device_id=self._device_id,
        )
        task_id = str(created.get("task_id", ""))
        fresh = await self.get_task(task_id)
        if fresh is not None:
            return fresh
        return dict_to_task({**created, "device_id": self._device_id})

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Fetch a SERVER task, or None when it does not exist (HTTP 404)."""
        try:
            return dict_to_task(await self._client.get_task(task_id))
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code == 404:
                return None
            raise

    async def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Task]:
        """List SERVER tasks, optionally filtered by status value."""
        return [dict_to_task(item) for item in await self._client.list_tasks(status=status, limit=limit)]

    async def update_progress(self, task_id: str, progress_pct: float) -> Optional[Task]:
        """Update SERVER-side progress percentage."""
        await self._client.update_task(task_id, progress_pct=progress_pct)
        return await self.get_task(task_id)

    async def start_task(self, task_id: str) -> Optional[Task]:
        """Mark a SERVER task as RUNNING."""
        await self._client.update_task(task_id, status=TaskStatus.RUNNING.value)
        return await self.get_task(task_id)

    async def complete_task(self, task_id: str, result: str) -> Optional[Task]:
        """Mark a SERVER task as COMPLETED with a result summary."""
        await self._client.update_task(
            task_id,
            status=TaskStatus.COMPLETED.value,
            result=result,
            progress_pct=100.0,
        )
        return await self.get_task(task_id)

    async def fail_task(self, task_id: str, error: str) -> Optional[Task]:
        """Mark a SERVER task as FAILED, preserving the errors history."""
        await self._client.update_task(task_id, status=TaskStatus.FAILED.value, error=error)
        return await self.get_task(task_id)

    async def cancel_task(self, task_id: str) -> Optional[Task]:
        """Cancel a SERVER task."""
        await self._client.cancel_task(task_id)
        return await self.get_task(task_id)

    async def pause_task(self, task_id: str) -> Optional[Task]:
        """Pause a SERVER task."""
        await self._client.pause_task(task_id)
        return await self.get_task(task_id)

    async def resume_task(self, task_id: str) -> Optional[Task]:
        """Resume a SERVER task."""
        await self._client.resume_task(task_id)
        return await self.get_task(task_id)
