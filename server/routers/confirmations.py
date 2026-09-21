"""Confirmations API Router — central single-use approval state (/api/confirmations).

Backed by the central SQLite `confirmations` table. Enforces the same
guarantees as the in-memory ConfirmationManager: single-use, session
binding, expiry, approved/denied, no replay, no cross-session misuse.
"""

import json
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger
from security.auth import require_node_auth

logger = get_logger("jarvis.api.confirmations")

router = APIRouter(prefix="/api/confirmations", tags=["confirmations"])

_memory: Optional[SQLiteMemoryProvider] = None


def _get_memory() -> SQLiteMemoryProvider:
    global _memory
    if _memory is None:
        _memory = SQLiteMemoryProvider()
    return _memory


class ConfirmationCreateRequest(BaseModel):
    confirmation_id: str = Field(..., description="Client-generated confirmation ID")
    tool_name: str = Field(..., description="Tool awaiting approval")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    security_level: str = Field(default="YELLOW", description="Security level")
    reason: str = Field(default="", description="Why confirmation is required")
    session_id: str = Field(default="", description="Owning session")
    call_id: str = Field(default="", description="Tool call ID")
    remaining_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Sibling calls of the same turn")
    timeout_seconds: float = Field(default=300.0, description="Expiry in seconds")


class ConfirmationResolveRequest(BaseModel):
    approved: bool = Field(..., description="Approval decision")


class ConfirmationConsumeRequest(BaseModel):
    session_id: str = Field(default="", description="Session claiming the confirmation")


def _row_to_response(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        arguments = json.loads(row.get("arguments_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        arguments = {}
    try:
        remaining = json.loads(row.get("remaining_calls_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        remaining = []
    approved = row.get("approved")
    return {
        "confirmation_id": row["confirmation_id"],
        "tool_name": row["tool_name"],
        "arguments": arguments if isinstance(arguments, dict) else {},
        "security_level": row.get("security_level", "YELLOW"),
        "reason": row.get("reason", ""),
        "session_id": row.get("session_id", ""),
        "call_id": row.get("call_id", ""),
        "remaining_calls": remaining if isinstance(remaining, list) else [],
        "created_at": row.get("created_at"),
        "timeout_seconds": row.get("timeout_seconds", 300.0),
        "approved": None if approved is None else bool(approved),
        "resolved_at": row.get("resolved_at"),
        "consumed": bool(row.get("consumed", 0)),
    }


@router.post("/", response_model=Dict[str, Any])
async def create_confirmation(
    request: ConfirmationCreateRequest,
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Create a pending confirmation."""
    try:
        memory = _get_memory()
        if await memory.get_confirmation(request.confirmation_id) is not None:
            raise HTTPException(status_code=409, detail="Confirmation already exists")
        await memory.create_confirmation(
            confirmation_id=request.confirmation_id,
            tool_name=request.tool_name,
            arguments_json=json.dumps(request.arguments),
            security_level=request.security_level,
            reason=request.reason,
            session_id=request.session_id,
            call_id=request.call_id,
            remaining_calls_json=json.dumps(request.remaining_calls),
            timeout_seconds=request.timeout_seconds,
        )
        return {"confirmation_id": request.confirmation_id, "created": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create confirmation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending", response_model=List[Dict[str, Any]])
async def list_pending_confirmations(
    _token: str = Depends(require_node_auth),
) -> List[Dict[str, Any]]:
    """List unresolved, unexpired, unconsumed confirmations."""
    try:
        memory = _get_memory()
        rows = await memory.list_pending_confirmations(now=time.time())
        return [_row_to_response(r) for r in rows]
    except Exception as e:
        logger.error("List pending confirmations error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{confirmation_id}", response_model=Dict[str, Any])
async def get_confirmation(
    confirmation_id: str,
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Get confirmation state (for polling approval)."""
    try:
        memory = _get_memory()
        row = await memory.get_confirmation(confirmation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Confirmation not found")
        return _row_to_response(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get confirmation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{confirmation_id}/resolve", response_model=Dict[str, Any])
async def resolve_confirmation(
    confirmation_id: str,
    request: ConfirmationResolveRequest,
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Approve or deny a pending confirmation."""
    try:
        memory = _get_memory()
        row = await memory.get_confirmation(confirmation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Confirmation not found")
        ok = await memory.resolve_confirmation(
            confirmation_id, approved=request.approved, now=time.time(),
        )
        if not ok:
            raise HTTPException(
                status_code=409,
                detail="Confirmation already resolved, consumed or expired",
            )
        return {"confirmation_id": confirmation_id, "approved": request.approved}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resolve confirmation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{confirmation_id}/consume", response_model=Dict[str, Any])
async def consume_confirmation(
    confirmation_id: str,
    request: ConfirmationConsumeRequest,
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Atomically consume a resolved confirmation (single-use).

    Returns 404 when missing, 409 when unresolved/consumed/expired or on
    session mismatch. Concurrent consumes: exactly one wins.
    """
    try:
        memory = _get_memory()
        row = await memory.consume_confirmation(
            confirmation_id, session_id=request.session_id, now=time.time(),
        )
        if row is None:
            existing = await memory.get_confirmation(confirmation_id)
            if existing is None:
                raise HTTPException(status_code=404, detail="Confirmation not found")
            raise HTTPException(
                status_code=409,
                detail="Confirmation not consumable (unresolved, consumed, expired or session mismatch)",
            )
        return _row_to_response(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Consume confirmation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup", response_model=Dict[str, Any])
async def cleanup_confirmations(
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Delete consumed or expired confirmations."""
    try:
        memory = _get_memory()
        removed = await memory.cleanup_confirmations(now=time.time())
        return {"removed": removed}
    except Exception as e:
        logger.error("Cleanup confirmations error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
