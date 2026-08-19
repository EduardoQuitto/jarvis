"""Tasks API Router — /api/tasks endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.task.manager import TaskManager
from core.contracts.enums import TaskStatus
from core.logger import get_logger

logger = get_logger("jarvis.api.tasks")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_task_manager: Optional[TaskManager] = None


def _get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


class TaskCreateRequest(BaseModel):
    objective: str = Field(..., description="Task objective")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")
    priority: str = Field(default="normal", description="Task priority")
    device_id: Optional[str] = Field(default=None, description="Device to execute on")


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    progress_pct: Optional[float] = None


@router.post("/", response_model=Dict[str, Any])
async def create_task(request: TaskCreateRequest) -> Dict[str, Any]:
    """Create a new task."""
    try:
        manager = _get_task_manager()
        task = await manager.create_task(
            objective=request.objective,
            context=request.context,
            priority=request.priority,
            device_id=request.device_id,
        )
        return {
            "task_id": task.task_id,
            "objective": task.objective,
            "status": task.status.value,
            "created_at": task.created_at.isoformat() if hasattr(task, 'created_at') else "",
        }
    except Exception as e:
        logger.error("Create task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[Dict[str, Any]])
async def list_tasks(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List tasks."""
    try:
        manager = _get_task_manager()
        tasks = await manager.list_all_tasks(limit=limit)
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        return [
            {
                "task_id": t.task_id,
                "objective": t.objective,
                "status": t.status.value,
                "progress_pct": t.progress_pct,
            }
            for t in tasks
        ]
    except Exception as e:
        logger.error("List tasks error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=Dict[str, Any])
async def get_task(task_id: str) -> Dict[str, Any]:
    """Get a specific task."""
    try:
        manager = _get_task_manager()
        task = await manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task.task_id,
            "objective": task.objective,
            "status": task.status.value,
            "progress_pct": task.progress_pct,
            "result": task.result,
            "errors": task.errors,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{task_id}", response_model=Dict[str, Any])
async def update_task(task_id: str, request: TaskUpdateRequest) -> Dict[str, Any]:
    """Update a task."""
    try:
        manager = _get_task_manager()
        updates = {}
        if request.status is not None:
            updates["status"] = request.status
        if request.result is not None:
            updates["result"] = request.result
        if request.error is not None:
            updates["error"] = request.error
        if request.progress_pct is not None:
            updates["progress_pct"] = request.progress_pct

        await manager.update_task(task_id, **updates)
        return {"status": "updated", "task_id": task_id}
    except Exception as e:
        logger.error("Update task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> Dict[str, Any]:
    """Cancel a task."""
    try:
        manager = _get_task_manager()
        await manager.cancel_task(task_id)
        return {"status": "cancelled", "task_id": task_id}
    except Exception as e:
        logger.error("Cancel task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/pause")
async def pause_task(task_id: str) -> Dict[str, Any]:
    """Pause a task."""
    try:
        manager = _get_task_manager()
        await manager.pause_task(task_id)
        return {"status": "paused", "task_id": task_id}
    except Exception as e:
        logger.error("Pause task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume")
async def resume_task(task_id: str) -> Dict[str, Any]:
    """Resume a paused task."""
    try:
        manager = _get_task_manager()
        await manager.resume_task(task_id)
        return {"status": "resumed", "task_id": task_id}
    except Exception as e:
        logger.error("Resume task error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
