"""Chat API Router — /api/chat endpoints for orchestrator interaction."""

import asyncio
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import get_settings
from core.contracts.enums import NodeRole
from core.contracts.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
)
from core.orchestrator.engine import Orchestrator
from core.llm.factory import create_llm_provider, create_router
from core.logger import get_logger
from security.auth import optional_node_auth
from server.compute import (
    ComputeUnavailable,
    forward_chat_send,
    forward_chat_stream,
    select_compute_node,
)

logger = get_logger("jarvis.api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Lazy-initialized orchestrator
_orchestrator: Optional[Orchestrator] = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        router_instance = create_router()
        _orchestrator = Orchestrator(router=router_instance)
    return _orchestrator


async def stream_orchestrator_events(orchestrator: Orchestrator, orch_request: OrchestratorRequest):
    """Yield SSE frames for one orchestrator stream (shared by chat and internal routes)."""
    try:
        async for event in orchestrator.stream_message(orch_request):
            yield f"event: {event.event_type.value.lower()}\ndata: {json.dumps(event.data, default=str)}\n\n"
    except asyncio.CancelledError:
        # Normal client disconnect: not a system error, just stop.
        logger.info("SSE client disconnected mid-stream")
        raise


def _is_gateway_mode() -> bool:
    """True when this process is the SERVER gateway (forwards chat to a CORE)."""
    return get_settings().node_role == NodeRole.SERVER


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(default=None, description="Existing conversation session ID")
    device_id: str = Field(default="api", description="Device ID")
    confirmation_id: Optional[str] = Field(default=None, description="Confirmation ID if responding to a pending confirmation")
    approved: Optional[bool] = Field(default=None, description="Whether the confirmation is approved (None = not a confirmation response)")


class ChatResponse(BaseModel):
    session_id: str
    response_text: str
    tool_calls: List[Dict[str, Any]] = []
    needs_confirmation: bool = False
    confirmation_id: Optional[str] = None
    confirmation_details: Optional[str] = None
    iterations_used: int = 0


def _to_chat_response(result: OrchestratorResponse) -> ChatResponse:
    """Map an orchestrator result to the public chat contract."""
    tool_calls_data = [
        {
            "tool_name": tc.tool_name,
            "success": tc.success,
            "error": tc.error,
            "execution_time_ms": tc.execution_time_ms,
        }
        for tc in (result.tool_calls_made or [])
    ]
    return ChatResponse(
        session_id=result.session_id,
        response_text=result.response_text,
        tool_calls=tool_calls_data,
        needs_confirmation=result.needs_confirmation,
        confirmation_id=result.confirmation_id,
        confirmation_details=result.confirmation_details,
        iterations_used=result.iterations_used,
    )


@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    _token: str = Depends(optional_node_auth),
) -> ChatResponse:
    """Send a message to the JARVIS orchestrator.

    On the SERVER node this acts as the central gateway: the request is
    forwarded to an eligible compute CORE (HTTP 503 when none is online).
    On any other node the local orchestrator answers directly.
    """
    try:
        if _is_gateway_mode():
            try:
                data = await forward_chat_send(request.model_dump())
            except ComputeUnavailable as e:
                raise HTTPException(status_code=503, detail=str(e))
            return ChatResponse(**data)

        orchestrator = _get_orchestrator()
        orch_request = OrchestratorRequest(
            message=request.message,
            session_id=request.session_id,
            device_id=request.device_id,
            confirmation_id=request.confirmation_id,
            approved=request.approved,
        )

        result = await orchestrator.process_message(orch_request)
        return _to_chat_response(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


class ChatStreamRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(default=None, description="Existing conversation session ID")
    device_id: str = Field(default="api", description="Device ID")
    confirmation_id: Optional[str] = Field(default=None, description="Confirmation ID if responding to a pending confirmation")
    approved: Optional[bool] = Field(default=None, description="Whether the confirmation is approved (None = not a confirmation response)")


@router.post("/stream")
async def stream_message(
    request: ChatStreamRequest,
    _token: str = Depends(optional_node_auth),
) -> StreamingResponse:
    """Stream orchestrator processing as Server-Sent Events (Phase 11).

    Same policy gates, persistence and confirmation flow as /send — only
    the delivery differs (live text_delta events instead of one response).
    A client disconnect cancels iteration cleanly; no background tasks exist.
    On the SERVER node the SSE bytes of a compute CORE are proxied through
    untouched (HTTP 503 when no CORE is online).
    """
    if _is_gateway_mode():
        try:
            node = await select_compute_node()
            if node is None:
                raise ComputeUnavailable("No eligible compute CORE is online.")
            proxy = forward_chat_stream(request.model_dump(), node=node)
        except ComputeUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e))
        return StreamingResponse(proxy, media_type="text/event-stream")

    orchestrator = _get_orchestrator()
    orch_request = OrchestratorRequest(
        message=request.message,
        session_id=request.session_id,
        device_id=request.device_id,
        confirmation_id=request.confirmation_id,
        approved=request.approved,
    )

    return StreamingResponse(
        stream_orchestrator_events(orchestrator, orch_request),
        media_type="text/event-stream",
    )


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approved: bool


@router.post("/confirm")
async def confirm_action(
    request: ConfirmRequest,
    _token: str = Depends(optional_node_auth),
) -> Dict[str, Any]:
    """Approve or deny a pending confirmation."""
    from core.orchestrator.confirmation import get_confirmation_manager

    manager = get_confirmation_manager()
    if request.approved:
        manager.approve(request.confirmation_id)
    else:
        manager.deny(request.confirmation_id)

    return {"status": "confirmed" if request.approved else "denied"}


@router.get("/confirm/pending")
async def list_pending_confirmations(
    _token: str = Depends(optional_node_auth),
) -> List[Dict[str, Any]]:
    """List all pending confirmation requests."""
    from core.orchestrator.confirmation import get_confirmation_manager

    manager = get_confirmation_manager()
    return manager.list_pending()
