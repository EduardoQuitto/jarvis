"""Memory API Router — /api/memory endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger
from security.auth import optional_node_auth

logger = get_logger("jarvis.api.memory")

router = APIRouter(prefix="/api/memory", tags=["memory"])

_memory: Optional[SQLiteMemoryProvider] = None


def _get_memory() -> SQLiteMemoryProvider:
    global _memory
    if _memory is None:
        _memory = SQLiteMemoryProvider()
    return _memory


class MemorySetRequest(BaseModel):
    key: str = Field(..., description="Memory key")
    value: Any = Field(..., description="Value to store")
    category: str = Field(default="general", description="Category")


class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, description="Max results")


@router.post("/set")
async def set_memory(
    request: MemorySetRequest,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Store a memory entry."""
    try:
        memory = _get_memory()
        await memory.set(key=request.key, value=request.value, category=request.category)
        return {"status": "stored", "key": request.key}
    except Exception as e:
        logger.error("Memory set error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{key}")
async def get_memory(
    key: str,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Retrieve a memory entry."""
    try:
        memory = _get_memory()
        entry = await memory.get(key)
        if not entry:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"key": entry.key, "value": entry.value, "category": entry.category}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Memory get error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_memory(
    request: MemorySearchRequest,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Search memory entries."""
    try:
        memory = _get_memory()
        results = await memory.search_memory(query=request.query, limit=request.limit)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error("Memory search error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
async def get_events(
    limit: int = 50,
    event_type: Optional[str] = None,
    _token: str = Depends(optional_node_auth),
) -> List[Dict[str, Any]]:
    """Get recent events."""
    try:
        memory = _get_memory()
        events = await memory.get_recent_events(limit=limit, event_type=event_type)
        return events
    except Exception as e:
        logger.error("Events error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{key}")
async def delete_memory(
    key: str,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Delete a memory entry."""
    try:
        memory = _get_memory()
        await memory.delete(key)
        return {"status": "deleted", "key": key}
    except Exception as e:
        logger.error("Memory delete error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
