"""Internal compute endpoints — CORE-only chat execution (/internal/chat).

Called by the SERVER gateway (never directly by end-user clients).
Requires node authentication. Reuses exactly the local Orchestrator
(process_message / stream_message): no duplicated policy, tools or LLM
routing. Refused on SERVER-role processes, which must not compute.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.config import get_settings
from core.contracts.enums import NodeRole
from core.contracts.orchestrator import OrchestratorRequest
from core.logger import get_logger
from security.auth import require_node_auth
from server.routers.chat import (
    ChatResponse,
    ChatStreamRequest,
    _get_orchestrator,
    _to_chat_response,
    stream_orchestrator_events,
)

logger = get_logger("jarvis.api.internal")

router = APIRouter(prefix="/internal/chat", tags=["internal-compute"])


def _require_compute_role() -> None:
    """Only non-SERVER nodes execute compute; the SERVER only routes."""
    if get_settings().node_role == NodeRole.SERVER:
        raise HTTPException(
            status_code=403,
            detail="Internal compute endpoints are disabled on SERVER-role nodes.",
        )


@router.post("/send", response_model=ChatResponse)
async def internal_send(
    request: ChatStreamRequest,
    _token: str = Depends(require_node_auth),
) -> ChatResponse:
    """Execute one orchestrator turn on this compute node."""
    _require_compute_role()
    try:
        orchestrator = _get_orchestrator()
        result = await orchestrator.process_message(
            OrchestratorRequest(
                message=request.message,
                session_id=request.session_id,
                device_id=request.device_id,
                confirmation_id=request.confirmation_id,
                approved=request.approved,
            )
        )
        return _to_chat_response(result)
    except Exception as e:
        logger.error("Internal chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Internal chat failed: {str(e)}")


@router.post("/stream")
async def internal_stream(
    request: ChatStreamRequest,
    _token: str = Depends(require_node_auth),
) -> StreamingResponse:
    """Stream one orchestrator turn on this compute node (SSE)."""
    _require_compute_role()
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
