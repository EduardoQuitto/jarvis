"""Confirmation Manager — pauses the agentic loop for user approval on sensitive actions.

Security improvements:
- Timestamps on all requests
- Timeout cleanup to prevent stale confirmations
- Reuse attempt logging
- Single-use enforcement with audit trail
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from core.logger import get_logger
from core.network.central_state_client import CentralStateClient, CentralStateError
from core.network.node_client import RemoteNodeError

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
        timeout: float = 300.0,
        remaining_calls: Optional[List[Dict[str, Any]]] = None,
    ):
        self.confirmation_id = confirmation_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.security_level = security_level
        self.reason = reason
        self.session_id = session_id
        self.call_id = call_id
        # Sibling tool calls of the same assistant turn, still unprocessed,
        # as {tool_name, arguments, call_id} dicts in order. Lets a resume
        # continue the turn instead of dropping them.
        self.remaining_calls: List[Dict[str, Any]] = list(remaining_calls or [])
        self.approved: Optional[bool] = None
        self.resolved = False
        self.created_at = time.time()
        self.resolved_at: Optional[float] = None
        self.timeout = timeout

    @property
    def is_expired(self) -> bool:
        """Check if this confirmation has expired."""
        if self.resolved:
            return False
        return (time.time() - self.created_at) > self.timeout

    def approve(self) -> None:
        """Approve the pending action."""
        if not self.resolved:
            self.resolved = True
            self.approved = True
            self.resolved_at = time.time()

    def deny(self) -> None:
        """Deny the pending action."""
        if not self.resolved:
            self.resolved = True
            self.approved = False
            self.resolved_at = time.time()


class ConfirmationManager:
    """Manages pending confirmation requests for YELLOW and RED actions.

    Authorization sources:
      1. REST operator direct — require_node_auth + confirmed=True (legacy compat).
      2. LLM/MCP flow — must use a valid confirmation_id (single-use, session-bound).

    Security improvements:
      - Timestamps on all requests for audit trail
      - Timeout cleanup for stale confirmations
      - Reuse attempt logging and blocking
      - Single-use enforcement

    Usage:
      1. request_confirmation(tool_name, args, ...) → returns confirmation_id
      2. Orchestrator returns needs_confirmation + cid to client
      3. Client calls /api/chat/confirm or /api/chat/send with confirmation_id
      4. Orchestrator calls consume(cid, session_id) → returns (approved, tool_name, args) or None
    """

    def __init__(self, default_timeout: float = 300.0, central_state=None):
        self._pending: Dict[str, ConfirmationRequest] = {}
        self._consumed: Set[str] = set()
        self._default_timeout = default_timeout
        # Optional central backend (CentralStateClient or compatible stub).
        # None = resolve from settings (central when enabled, else RAM).
        # False = force RAM even when central is enabled (tests/dev).
        self._central_state = central_state
        self._central_resolved = False

    def _get_central(self):
        """Resolve the central backend once (None = RAM mode)."""
        if not self._central_resolved:
            self._central_resolved = True
            if self._central_state is False:
                self._central_state = None
            elif self._central_state is None:
                from core.network.central_state_client import CentralStateClient
                self._central_state = CentralStateClient.from_settings()
        return self._central_state

    def _central_client(self):
        """Underlying RemoteNodeClient for sync central calls, or None."""
        central = self._get_central()
        return central._client if central is not None else None

    @staticmethod
    def _central_required() -> bool:
        from core.config import get_settings
        return get_settings().central_state_required

    def _central_or_raise(self, operation: str, error) -> None:
        """Required mode: explicit failure. Otherwise: warn, caller falls back to RAM."""
        if self._central_required():
            from core.network.central_state_client import CentralStateError
            raise CentralStateError(
                f"Central state required but unavailable during {operation} "
                f"({error.kind}): {error.message}",
                kind=error.kind,
                status_code=getattr(error, "status_code", None),
            ) from error
        logger.warning(
            "Central confirmations failed during %s (%s); falling back to RAM",
            operation, error.kind,
        )

    async def request_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        security_level: str,
        reason: str = "",
        session_id: str = "",
        call_id: str = "",
        timeout: Optional[float] = None,
        remaining_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Create a confirmation request.

        Returns the confirmation_id to include in the orchestrator response.
        remaining_calls carries the sibling tool calls of the same assistant
        turn so a resume can continue them instead of dropping them.
        """
        cid = f"confirm-{uuid.uuid4().hex[:8]}"
        central = self._get_central()
        if central is not None:
            # This method is async, so the async central client fits directly.
            try:
                await central.confirmation_create({
                    "confirmation_id": cid,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "security_level": security_level,
                    "reason": reason,
                    "session_id": session_id,
                    "call_id": call_id,
                    "remaining_calls": list(remaining_calls or []),
                    "timeout_seconds": timeout or self._default_timeout,
                })
                logger.info("Central confirmation requested: %s (%s) — id: %s, session: %s",
                            tool_name, security_level, cid, session_id)
                return cid
            except CentralStateError as e:
                self._central_or_raise("request_confirmation", e)
        req = ConfirmationRequest(
            confirmation_id=cid,
            tool_name=tool_name,
            arguments=arguments,
            security_level=security_level,
            reason=reason,
            session_id=session_id,
            call_id=call_id,
            timeout=timeout or self._default_timeout,
            remaining_calls=remaining_calls,
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
          - Not expired

        Returns a dict with {approved, tool_name, arguments, call_id,
        remaining_calls} or None if invalid.
        """
        central_result = self._consume_central(confirmation_id, session_id)
        if central_result != "local":
            return central_result
        req = self._pending.get(confirmation_id)
        if req is None:
            logger.warning("Confirmation %s not found", confirmation_id)
            return None

        # Block reuse attempts
        if confirmation_id in self._consumed:
            logger.warning(
                "Confirmation %s reuse attempt blocked — id already consumed",
                confirmation_id,
            )
            return None

        if not req.resolved:
            if req.is_expired:
                logger.warning("Confirmation %s expired", confirmation_id)
                del self._pending[confirmation_id]
                return None
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
            "remaining_calls": list(req.remaining_calls),
        }

        # Single-use: track and remove
        self._consumed.add(confirmation_id)
        del self._pending[confirmation_id]
        logger.info("Confirmation %s consumed: approved=%s", confirmation_id, req.approved)
        return result

    def _consume_central(self, confirmation_id: str, session_id: str):
        """Consume via central state. Returns dict, None (unavailable), or raises."""
        client = self._central_client()
        if client is None:
            return "local"
        try:
            record = client._request_sync(
                "POST", f"/api/confirmations/{confirmation_id}/consume",
                {"session_id": session_id},
            )
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code in (404, 409):
                return None
            self._central_or_raise("consume", e)
            return "local"
        arguments = record.get("arguments")
        remaining = record.get("remaining_calls")
        return {
            "approved": record.get("approved"),
            "tool_name": record.get("tool_name"),
            "arguments": arguments if isinstance(arguments, dict) else {},
            "call_id": record.get("call_id", ""),
            "security_level": record.get("security_level", "YELLOW"),
            "remaining_calls": remaining if isinstance(remaining, list) else [],
        }

    def _resolve_central(self, confirmation_id: str, approved: bool) -> Optional[bool]:
        """Resolve via central state. None = unavailable (caller falls back to RAM)."""
        client = self._central_client()
        if client is None:
            return None
        try:
            client._request_sync(
                "POST", f"/api/confirmations/{confirmation_id}/resolve",
                {"approved": approved},
            )
            return True
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code in (404, 409):
                return False
            self._central_or_raise("resolve", e)
            return None

    def approve(self, confirmation_id: str) -> bool:
        """Approve a pending confirmation. Returns True if found."""
        resolved = self._resolve_central(confirmation_id, True)
        if resolved is not None:
            return resolved
        req = self._pending.get(confirmation_id)
        if req:
            if req.is_expired:
                logger.warning("Confirmation %s expired, cannot approve", confirmation_id)
                del self._pending[confirmation_id]
                return False
            req.approve()
            logger.info("Confirmation %s approved", confirmation_id)
            return True
        return False

    def deny(self, confirmation_id: str) -> bool:
        """Deny a pending confirmation. Returns True if found."""
        resolved = self._resolve_central(confirmation_id, False)
        if resolved is not None:
            return resolved
        req = self._pending.get(confirmation_id)
        if req:
            if req.is_expired:
                logger.warning("Confirmation %s expired, cannot deny", confirmation_id)
                del self._pending[confirmation_id]
                return False
            req.deny()
            logger.info("Confirmation %s denied", confirmation_id)
            return True
        return False

    async def wait_for_confirmation(self, confirmation_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for a confirmation to be approved or denied (blocking with timeout).

        Returns True if approved, False if denied or timed out.
        """
        central = self._get_central()
        if central is not None:
            timeout = timeout or self._default_timeout
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    record = await central.confirmation_get(confirmation_id)
                except CentralStateError as e:
                    self._central_or_raise("wait_for_confirmation", e)
                    return False
                if record is None:
                    return False
                if record.get("resolved_at") is not None:
                    return bool(record.get("approved"))
                await asyncio.sleep(0.05)
            return False
        req = self._pending.get(confirmation_id)
        if not req:
            return False
        if req.resolved:
            return req.approved or False
        # Poll until resolved or timeout
        timeout = timeout or self._default_timeout
        deadline = asyncio.get_event_loop().time() + timeout
        while not req.resolved and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.05)
        return req.approved or False

    def get_pending(self, confirmation_id: str) -> Optional[ConfirmationRequest]:
        """Get a pending confirmation request."""
        client = self._central_client()
        if client is not None:
            try:
                record = client._request_sync("GET", f"/api/confirmations/{confirmation_id}")
            except RemoteNodeError as e:
                if e.kind == "client_error" and e.status_code == 404:
                    return None
                self._central_or_raise("get_pending", e)
                return self._pending.get(confirmation_id)
            if record.get("resolved_at") is not None or record.get("consumed"):
                return None
            req = ConfirmationRequest(
                confirmation_id=record["confirmation_id"],
                tool_name=record.get("tool_name", ""),
                arguments=record.get("arguments") or {},
                security_level=record.get("security_level", "YELLOW"),
                reason=record.get("reason", ""),
                session_id=record.get("session_id", ""),
                call_id=record.get("call_id", ""),
                timeout=record.get("timeout_seconds", self._default_timeout),
                remaining_calls=record.get("remaining_calls") or [],
            )
            req.created_at = record.get("created_at", req.created_at)
            return req
        return self._pending.get(confirmation_id)

    def list_pending(self) -> list:
        """List all pending confirmation requests."""
        client = self._central_client()
        if client is not None:
            try:
                records = client._request_sync("GET", "/api/confirmations/pending")
                return [
                    {
                        "confirmation_id": r["confirmation_id"],
                        "tool_name": r.get("tool_name", ""),
                        "arguments": r.get("arguments") or {},
                        "security_level": r.get("security_level", "YELLOW"),
                        "reason": r.get("reason", ""),
                        "session_id": r.get("session_id", ""),
                        "created_at": r.get("created_at", 0.0),
                        "is_expired": False,
                    }
                    for r in records
                ]
            except RemoteNodeError as e:
                self._central_or_raise("list_pending", e)
        return [
            {
                "confirmation_id": req.confirmation_id,
                "tool_name": req.tool_name,
                "arguments": req.arguments,
                "security_level": req.security_level,
                "reason": req.reason,
                "session_id": req.session_id,
                "created_at": req.created_at,
                "is_expired": req.is_expired,
            }
            for req in self._pending.values()
            if not req.resolved
        ]

    def cleanup(self) -> int:
        """Remove resolved and expired confirmations. Returns number removed."""
        client = self._central_client()
        if client is not None:
            try:
                removed = client._request_sync("POST", "/api/confirmations/cleanup")
                return int(removed.get("removed", 0))
            except RemoteNodeError as e:
                self._central_or_raise("cleanup", e)
        before = len(self._pending)
        to_remove = []
        for k, v in self._pending.items():
            if v.resolved or v.is_expired:
                to_remove.append(k)
        for k in to_remove:
            del self._pending[k]
        removed = before - len(self._pending)
        if removed:
            logger.info("Cleanup removed %d stale confirmations", removed)
        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Get confirmation manager statistics for audit."""
        return {
            "pending_count": len(self._pending),
            "consumed_count": len(self._consumed),
            "pending_ids": list(self._pending.keys()),
        }


# Global confirmation manager
_confirmation_manager: Optional[ConfirmationManager] = None


def get_confirmation_manager() -> ConfirmationManager:
    """Access the global confirmation manager."""
    global _confirmation_manager
    if _confirmation_manager is None:
        _confirmation_manager = ConfirmationManager()
    return _confirmation_manager
