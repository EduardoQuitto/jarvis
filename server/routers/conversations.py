"""Conversations API Router — central conversation persistence (/api/conversations).

Reuses the existing SQLite schema (conversations + conversation_messages).
No new database, no duplicated persistence logic.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger
from security.auth import optional_node_auth

logger = get_logger("jarvis.api.conversations")

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_memory: Optional[SQLiteMemoryProvider] = None


def _get_memory() -> SQLiteMemoryProvider:
    global _memory
    if _memory is None:
        _memory = SQLiteMemoryProvider()
    return _memory


class ConversationCreateRequest(BaseModel):
    conversation_id: str = Field(..., description="Client-generated conversation ID")
    title: Optional[str] = Field(default=None, description="Conversation title")
    device_id: Optional[str] = Field(default=None, description="Originating device")


class ConversationMessageRequest(BaseModel):
    role: str = Field(..., description="Message role: user, assistant, tool, system")
    content: str = Field(default="", description="Text content")
    tool_calls_json: Optional[str] = Field(default=None, description="Serialized tool calls")
    tool_call_id: Optional[str] = Field(default=None, description="Tool call ID for tool responses")
    name: Optional[str] = Field(default=None, description="Tool name for tool responses")


@router.post("/", response_model=Dict[str, Any])
async def create_conversation(
    request: ConversationCreateRequest,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Create a new conversation session."""
    try:
        memory = _get_memory()
        await memory.create_conversation(
            request.conversation_id, title=request.title, device_id=request.device_id,
        )
        return {"id": request.conversation_id, "created": True}
    except Exception as e:
        logger.error("Create conversation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[Dict[str, Any]])
async def list_conversations(
    limit: int = 20,
    _token: str = Depends(optional_node_auth),
) -> List[Dict[str, Any]]:
    """List recent conversations."""
    try:
        memory = _get_memory()
        rows = await memory.list_conversations(limit=limit)
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "device_id": r["device_id"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("List conversations error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=Dict[str, Any])
async def get_conversation(
    conversation_id: str,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Get a conversation session."""
    try:
        memory = _get_memory()
        rows = await memory.list_conversations(limit=1000)
        match = next((r for r in rows if r["id"] == conversation_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            "id": match["id"],
            "title": match["title"],
            "device_id": match["device_id"],
            "message_count": match["message_count"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get conversation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}/messages", response_model=List[Dict[str, Any]])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    _token: str = Depends(optional_node_auth),
) -> List[Dict[str, Any]]:
    """Get recent messages of a conversation, oldest first."""
    try:
        memory = _get_memory()
        rows = await memory.get_conversation_history(conversation_id, limit=limit)
        if not rows:
            # Distinguish unknown conversation from an empty one
            all_rows = await memory.list_conversations(limit=1000)
            if not any(r["id"] == conversation_id for r in all_rows):
                raise HTTPException(status_code=404, detail="Conversation not found")
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "tool_calls_json": r["tool_calls_json"],
                "tool_call_id": r["tool_call_id"],
                "name": r["name"],
            }
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get conversation messages error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conversation_id}/messages", response_model=Dict[str, Any])
async def append_conversation_message(
    conversation_id: str,
    request: ConversationMessageRequest,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Append one message, preserving tool-call sequence fields verbatim."""
    try:
        memory = _get_memory()
        await memory.append_conversation_message(
            conversation_id,
            request.role,
            request.content,
            tool_calls_json=request.tool_calls_json,
            tool_call_id=request.tool_call_id,
            name=request.name,
        )
        return {"stored": True, "conversation_id": conversation_id}
    except Exception as e:
        logger.error("Append conversation message error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
