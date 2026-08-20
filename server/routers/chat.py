"""Chat API Router — /api/chat endpoints for orchestrator interaction."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.contracts.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
)
from core.orchestrator.engine import Orchestrator
from core.llm.factory import create_llm_provider, create_router
from core.logger import get_logger
from security.auth import optional_node_auth

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


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(default=None, description="Existing conversation session ID")
    device_id: str = Field(default="api", description="Device ID")
    confirmed: bool = Field(default=False, description="Confirmation for pending actions")
    confirmation_id: Optional[str] = Field(default=None, description="Confirmation ID if confirming")


class ChatResponse(BaseModel):
    session_id: str
    response_text: str
    tool_calls: List[Dict[str, Any]] = []
    needs_confirmation: bool = False
    confirmation_id: Optional[str] = None
    confirmation_details: Optional[str] = None
    iterations_used: int = 0


@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    _token: str = Depends(optional_node_auth),
) -> ChatResponse:
    """Send a message to the JARVIS orchestrator."""
    try:
        orchestrator = _get_orchestrator()
        orch_request = OrchestratorRequest(
            message=request.message,
            session_id=request.session_id,
            device_id=request.device_id,
            confirmed=request.confirmed,
            confirmation_id=request.confirmation_id,
        )

        result = await orchestrator.process_message(orch_request)

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

    except Exception as e:
        logger.error("Chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


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
