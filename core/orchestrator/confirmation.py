"""Confirmation Manager — pauses the agentic loop for user approval on sensitive actions."""

import asyncio
import uuid
from typing import Any, Dict, Optional

from core.logger import get_logger

logger = get_logger("jarvis.confirmation")


class ConfirmationRequest:
    """A pending confirmation request."""

    def __init__(
        self,
        confirmation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        security_level: str,
        reason: str = "",
        session_id: str = "",
        call_id: str = "",
    ):
        self.confirmation_id = confirmation_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.security_level = security_level
        self.reason = reason
        self.session_id = session_id
        self.call_id = call_id
        self.approved: Optional[bool] = None
        self.resolved = False

    def approve(self) -> None:
        """Approve the pending action."""
        if not self.resolved:
            self.resolved = True
            self.approved = True

    def deny(self) -> None:
        """Deny the pending action."""
        if not self.resolved:
            self.resolved = True
            self.approved = False


class ConfirmationManager:
    """Manages pending confirmation requests for YELLOW and RED actions.

    Authorization sources:
      1. REST operator direct — require_node_auth + confirmed=True (legacy compat).
      2. LLM/MCP flow — must use a valid confirmation_id (single-use, session-bound).

    Usage:
      1. request_confirmation(tool_name, args, ...) → returns confirmation_id
      2. Orchestrator returns needs_confirmation + cid to client
      3. Client calls /api/chat/confirm or /api/chat/send with confirmation_id
      4. Orchestrator calls consume(cid, session_id) → returns (approved, tool_name, args) or None
    """

    def __init__(self, default_timeout: float = 300.0):
        self._pending: Dict[str, ConfirmationRequest] = {}
        self._default_timeout = default_timeout

    async def request_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        security_level: str,
        reason: str = "",
        session_id: str = "",
        call_id: str = "",
    ) -> str:
        """Create a confirmation request.

        Returns the confirmation_id to include in the orchestrator response.
        """
        cid = f"confirm-{uuid.uuid4().hex[:8]}"
        req = ConfirmationRequest(
            confirmation_id=cid,
            tool_name=tool_name,
            arguments=arguments,
            security_level=security_level,
            reason=reason,
            session_id=session_id,
            call_id=call_id,
        )
        self._pending[cid] = req
        logger.info("Confirmation requested: %s (%s) — id: %s, session: %s",
                     tool_name, security_level, cid, session_id)
        return cid

    def consume(self, confirmation_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Consume an approved confirmation.

        Validates:
          - Confirmation exists and is resolved (approved or denied)
          - Session ID matches (prevents cross-session misuse)
          - Single-use: removes the request after consumption

        Returns a dict with {approved, tool_name, arguments, call_id} or None if invalid.
        """
        req = self._pending.get(confirmation_id)
        if req is None:
            logger.warning("Confirmation %s not found", confirmation_id)
            return None

        if not req.resolved:
            logger.warning("Confirmation %s not yet resolved", confirmation_id)
            return None

        if session_id and req.session_id and req.session_id != session_id:
            logger.warning("Confirmation %s session mismatch: expected %s, got %s",
                           confirmation_id, req.session_id, session_id)
            return None

        result = {
            "approved": req.approved,
            "tool_name": req.tool_name,
            "arguments": req.arguments,
            "call_id": req.call_id,
            "security_level": req.security_level,
        }

        # Single-use: remove after consumption
        del self._pending[confirmation_id]
        logger.info("Confirmation %s consumed: approved=%s", confirmation_id, req.approved)
        return result

    def approve(self, confirmation_id: str) -> bool:
        """Approve a pending confirmation. Returns True if found."""
        req = self._pending.get(confirmation_id)
        if req:
            req.approve()
            logger.info("Confirmation %s approved", confirmation_id)
            return True
        return False

    def deny(self, confirmation_id: str) -> bool:
        """Deny a pending confirmation. Returns True if found."""
        req = self._pending.get(confirmation_id)
        if req:
            req.deny()
            logger.info("Confirmation %s denied", confirmation_id)
            return True
        return False

    async def wait_for_confirmation(self, confirmation_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for a confirmation to be approved or denied (blocking with timeout).

        Returns True if approved, False if denied or timed out.
        """
        import asyncio as _asyncio
        req = self._pending.get(confirmation_id)
        if not req:
            return False
        if req.resolved:
            return req.approved or False
        # Poll until resolved or timeout
        timeout = timeout or self._default_timeout
        deadline = _asyncio.get_event_loop().time() + timeout
        while not req.resolved and _asyncio.get_event_loop().time() < deadline:
            await _asyncio.sleep(0.05)
        return req.approved or False

    def get_pending(self, confirmation_id: str) -> Optional[ConfirmationRequest]:
        """Get a pending confirmation request."""
        return self._pending.get(confirmation_id)

    def list_pending(self) -> list:
        """List all pending confirmation requests."""
        return [
            {
                "confirmation_id": req.confirmation_id,
                "tool_name": req.tool_name,
                "arguments": req.arguments,
                "security_level": req.security_level,
                "reason": req.reason,
                "session_id": req.session_id,
            }
            for req in self._pending.values()
            if not req.resolved
        ]

    def cleanup(self) -> int:
        """Remove resolved confirmations. Returns number removed."""
        before = len(self._pending)
        self._pending = {k: v for k, v in self._pending.items() if not v.resolved}
        return before - len(self._pending)


# Global confirmation manager
_confirmation_manager: Optional[ConfirmationManager] = None


def get_confirmation_manager() -> ConfirmationManager:
    """Access the global confirmation manager."""
    global _confirmation_manager
    if _confirmation_manager is None:
        _confirmation_manager = ConfirmationManager()
    return _confirmation_manager
