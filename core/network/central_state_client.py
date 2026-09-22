"""Central state client (CORE -> SERVER source of truth).

Thin layer over RemoteNodeClient for conversations, memory and
confirmations. It adds no HTTP logic of its own: authentication, timeout
and transport error handling stay in RemoteNodeClient.

Failures are never hidden: every method raises CentralStateError
(wrapping RemoteNodeError) on transport problems, and unexpected payloads
raise CentralStateError(kind="invalid_response"). It never invents state.
"""

from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.logger import get_logger
from core.network.node_client import RemoteNodeClient, RemoteNodeError

logger = get_logger("jarvis.network.central_state")


class CentralStateError(Exception):
    """Standardized error for central-state operations."""

    def __init__(
        self,
        message: str,
        kind: str = "unknown",
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status_code = status_code

    @classmethod
    def from_remote_error(cls, operation: str, error: RemoteNodeError) -> "CentralStateError":
        return cls(
            f"Central state unavailable during {operation} "
            f"({error.kind}): {error.message}",
            kind=error.kind,
            status_code=error.status_code,
        )


class CentralStateClient:
    """Administers SERVER-persisted conversations, memory and confirmations."""

    def __init__(self, client: RemoteNodeClient):
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings=None,
        client: Optional[RemoteNodeClient] = None,
    ) -> Optional["CentralStateClient"]:
        """Build from settings, or None when central state is disabled."""
        settings = settings or get_settings()
        if not settings.central_state_enabled or not settings.server_url:
            return None
        return cls(
            client=client or RemoteNodeClient(
                base_url=settings.server_url,
                api_key=settings.server_api_key,
                timeout=settings.server_timeout,
            )
        )

    # --- conversations ---

    async def create_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return await self._client.create_conversation(
                conversation_id=conversation_id, title=title, device_id=device_id,
            )
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("create_conversation", e) from e

    async def list_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            return await self._client.list_conversations(limit=limit)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("list_conversations", e) from e

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._client.get_conversation(conversation_id)
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code == 404:
                return None
            raise CentralStateError.from_remote_error("get_conversation", e) from e

    async def get_messages(self, conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            return await self._client.get_conversation_messages(conversation_id, limit=limit)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("get_messages", e) from e

    async def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls_json: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return await self._client.append_conversation_message(
                conversation_id, role, content,
                tool_calls_json=tool_calls_json, tool_call_id=tool_call_id, name=name,
            )
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("append_message", e) from e

    # --- memory ---

    async def memory_set(self, key: str, value: Any, category: str = "general") -> Dict[str, Any]:
        try:
            return await self._client.memory_set(key=key, value=value, category=category)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("memory_set", e) from e

    async def memory_get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._client.memory_get(key)
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code == 404:
                return None
            raise CentralStateError.from_remote_error("memory_get", e) from e

    async def memory_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            return await self._client.memory_search(query=query, limit=limit)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("memory_search", e) from e

    async def memory_delete(self, key: str) -> bool:
        try:
            result = await self._client.memory_delete(key)
            return bool(result.get("deleted", True))
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("memory_delete", e) from e

    # --- confirmations ---

    async def confirmation_create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await self._client.confirmation_create(payload)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("confirmation_create", e) from e

    async def confirmation_resolve(self, confirmation_id: str, approved: bool) -> Dict[str, Any]:
        try:
            return await self._client.confirmation_resolve(confirmation_id, approved=approved)
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("confirmation_resolve", e) from e

    async def confirmation_get(self, confirmation_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._client.confirmation_get(confirmation_id)
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code == 404:
                return None
            raise CentralStateError.from_remote_error("confirmation_get", e) from e

    async def confirmation_consume(self, confirmation_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Atomically consume a confirmation, or None when unavailable."""
        try:
            return await self._client.confirmation_consume(confirmation_id, session_id=session_id)
        except RemoteNodeError as e:
            if e.kind == "client_error" and e.status_code in (404, 409):
                return None
            raise CentralStateError.from_remote_error("confirmation_consume", e) from e

    async def confirmations_pending(self) -> List[Dict[str, Any]]:
        try:
            return await self._client.confirmations_pending()
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("confirmations_pending", e) from e

    async def confirmations_cleanup(self) -> int:
        try:
            result = await self._client.confirmations_cleanup()
            return int(result.get("removed", 0))
        except RemoteNodeError as e:
            raise CentralStateError.from_remote_error("confirmations_cleanup", e) from e
