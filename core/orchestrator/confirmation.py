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
        reason: str,
    ):
        self.confirmation_id = confirmation_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.security_level = security_level
        self.reason = reason
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.resolved = False

    def approve(self) -> None:
        """Approve the pending action."""
        if not self.resolved:
            self.resolved = True
            self.future.set_result(True)

    def deny(self) -> None:
        """Deny the pending action."""
        if not self.resolved:
            self.resolved = True
            self.future.set_result(False)


class ConfirmationManager:
    """Manages pending confirmation requests for YELLOW and RED actions.

    When a tool requires confirmation, the orchestrator pauses and creates a
    ConfirmationRequest. The UI or user can then approve or deny it.
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
    ) -> str:
        """Create a confirmation request and wait for approval.

        Returns the confirmation_id. The caller should then await wait_for_confirmation().
        """
        cid = f"confirm-{uuid.uuid4().hex[:8]}"
        req = ConfirmationRequest(
            confirmation_id=cid,
            tool_name=tool_name,
            arguments=arguments,
            security_level=security_level,
            reason=reason,
        )
        self._pending[cid] = req
        logger.info("Confirmation requested: %s (%s) — id: %s", tool_name, security_level, cid)
        return cid

    async def wait_for_confirmation(self, confirmation_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for a confirmation to be approved or denied.

        Returns True if approved, False if denied or timed out.
        """
        req = self._pending.get(confirmation_id)
        if not req:
            logger.warning("Confirmation %s not found", confirmation_id)
            return False

        timeout = timeout or self._default_timeout
        try:
            result = await asyncio.wait_for(req.future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning("Confirmation %s timed out", confirmation_id)
            req.resolved = True
            req.future.set_result(False)
            return False

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
