"""Async HTTP client for the CORE -> SERVER bridge.

This module ONLY transports already-authorized tool calls to the remote
SERVER node. It never executes tools locally and never duplicates
PolicyEngine logic — final authorization always happens on the SERVER
via POST /tools/execute + ToolRegistry/PolicyEngine.

All network/HTTP/JSON failures are normalized to RemoteNodeError so the
Orchestrator never receives raw httpx exceptions.
"""

from typing import Any, Dict, List, Optional

import httpx

from core.logger import get_logger

logger = get_logger("jarvis.network.node_client")


class RemoteNodeError(Exception):
    """Standardized error for CORE -> SERVER communication failures."""

    def __init__(
        self,
        message: str,
        kind: str = "unknown",
        status_code: Optional[int] = None,
        details: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status_code = status_code
        self.details = details


class RemoteNodeClient:
    """Async client for a remote JARVIS SERVER node.

    Args:
        base_url: Base URL of the SERVER (e.g. http://192.168.0.13:8000).
        api_key: Bearer token used for SERVER authentication.
        timeout: Per-request timeout in seconds.
        transport: Optional httpx transport (used by tests with MockTransport).
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: float = 30.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self._transport = transport

    @property
    def is_configured(self) -> bool:
        """Whether a remote SERVER URL was configured."""
        return bool(self.base_url)

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._build_headers(),
            transport=self._transport,
        )

    def _request_sync(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Synchronous twin of _request for sync contexts (e.g. ConfirmationManager).

        Same authentication, timeout and RemoteNodeError semantics; never
        returns raw httpx exceptions. Must not be called from async code.
        """
        if not self.base_url:
            raise RemoteNodeError(
                "Remote SERVER is not configured (server_url is empty).",
                kind="configuration",
            )
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self._build_headers(),
                transport=self._transport,
            ) as client:
                response = client.request(method, url, json=payload, params=params)
        except httpx.TimeoutException as e:
            logger.error("Remote SERVER timeout (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER request timed out after {self.timeout}s: {method} {path}",
                kind="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.error("Remote SERVER connection refused (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER connection refused at {self.base_url}: {e}",
                kind="connection",
            ) from e
        except httpx.NetworkError as e:
            logger.error("Remote SERVER network error (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER network error: {e}",
                kind="connection",
            ) from e
        except RemoteNodeError:
            raise
        except Exception as e:
            logger.error("Remote SERVER transport error (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER transport error: {e}",
                kind="connection",
            ) from e

        status = response.status_code
        if status in (401, 403):
            raise RemoteNodeError(
                f"Remote SERVER authentication failed (HTTP {status}).",
                kind="auth",
                status_code=status,
                details=response.text[:500],
            )
        if 400 <= status < 500:
            raise RemoteNodeError(
                f"Remote SERVER rejected the request (HTTP {status}).",
                kind="client_error",
                status_code=status,
                details=response.text[:500],
            )
        if 500 <= status:
            raise RemoteNodeError(
                f"Remote SERVER internal error (HTTP {status}).",
                kind="server_error",
                status_code=status,
                details=response.text[:500],
            )

        try:
            return response.json()
        except Exception as e:
            raise RemoteNodeError(
                f"Remote SERVER returned invalid JSON for {method} {path}.",
                kind="invalid_response",
                status_code=status,
                details=response.text[:500],
            ) from e

    async def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform one HTTP request and return the parsed JSON body."""
        if not self.base_url:
            raise RemoteNodeError(
                "Remote SERVER is not configured (server_url is empty).",
                kind="configuration",
            )
        url = f"{self.base_url}{path}"
        try:
            async with self._build_client() as client:
                response = await client.request(method, url, json=payload, params=params)
        except httpx.TimeoutException as e:
            logger.error("Remote SERVER timeout (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER request timed out after {self.timeout}s: {method} {path}",
                kind="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.error("Remote SERVER connection refused (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER connection refused at {self.base_url}: {e}",
                kind="connection",
            ) from e
        except httpx.NetworkError as e:
            logger.error("Remote SERVER network error (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER network error: {e}",
                kind="connection",
            ) from e
        except RemoteNodeError:
            raise
        except Exception as e:
            logger.error("Remote SERVER transport error (%s %s): %s", method, path, str(e))
            raise RemoteNodeError(
                f"Remote SERVER transport error: {e}",
                kind="connection",
            ) from e

        status = response.status_code
        if status in (401, 403):
            raise RemoteNodeError(
                f"Remote SERVER authentication failed (HTTP {status}).",
                kind="auth",
                status_code=status,
                details=response.text[:500],
            )
        if 400 <= status < 500:
            raise RemoteNodeError(
                f"Remote SERVER rejected the request (HTTP {status}).",
                kind="client_error",
                status_code=status,
                details=response.text[:500],
            )
        if 500 <= status:
            raise RemoteNodeError(
                f"Remote SERVER internal error (HTTP {status}).",
                kind="server_error",
                status_code=status,
                details=response.text[:500],
            )

        try:
            return response.json()
        except Exception as e:
            raise RemoteNodeError(
                f"Remote SERVER returned invalid JSON for {method} {path}.",
                kind="invalid_response",
                status_code=status,
                details=response.text[:500],
            ) from e

    async def health(self) -> Dict[str, Any]:
        """GET /health from the remote SERVER."""
        data = await self._request("GET", "/health")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /health returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def list_devices(self) -> List[Dict[str, Any]]:
        """GET /api/devices/ from the remote SERVER."""
        data = await self._request("GET", "/api/devices/")
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER /api/devices/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def list_tools(self) -> List[Dict[str, Any]]:
        """GET /tools from the remote SERVER."""
        data = await self._request("GET", "/tools")
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER /tools returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def register_device(
        self,
        *,
        device_id: str,
        name: str = "",
        device_type: str = "CORE",
        capabilities: Optional[List[str]] = None,
        version: str = "0.5.0",
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """POST /api/devices/ on the remote SERVER.

        ip_address/port are only sent when explicitly provided (and port > 0).
        The Core never invents an inbound endpoint: without explicit
        advertise settings, no IP/port is announced.
        """
        if not device_id:
            raise RemoteNodeError(
                "Invalid device_id: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {
            "device_id": device_id,
            "name": name,
            "device_type": device_type,
            "capabilities": capabilities or [],
            "version": version,
        }
        if ip_address:
            payload["ip_address"] = ip_address
        if port and port > 0:
            payload["port"] = port
        data = await self._request("POST", "/api/devices/", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/devices/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def heartbeat(
        self,
        *,
        device_id: str,
        status: str = "ONLINE",
        capabilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /api/devices/heartbeat on the remote SERVER."""
        if not device_id:
            raise RemoteNodeError(
                "Invalid device_id: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {
            "device_id": device_id,
            "status": status,
            "capabilities": capabilities or [],
        }
        data = await self._request("POST", "/api/devices/heartbeat", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/devices/heartbeat returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def create_task(
        self,
        *,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        conversation_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /api/tasks/ on the remote SERVER. Transport only."""
        if not objective:
            raise RemoteNodeError(
                "Invalid objective: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {
            "objective": objective,
            "priority": priority,
        }
        if context is not None:
            payload["context"] = context
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        if device_id is not None:
            payload["device_id"] = device_id
        data = await self._request("POST", "/api/tasks/", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/tasks/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """GET /api/tasks/ on the remote SERVER. Transport only."""
        params: Dict[str, Any] = {"limit": limit}
        if status is not None:
            params["status"] = status
        data = await self._request("GET", "/api/tasks/", params=params)
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER /api/tasks/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """GET /api/tasks/{task_id} on the remote SERVER. Transport only."""
        if not task_id:
            raise RemoteNodeError(
                "Invalid task_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("GET", f"/api/tasks/{task_id}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                f"Remote SERVER /api/tasks/{task_id} returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        result: Optional[str] = None,
        progress_pct: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """PATCH /api/tasks/{task_id} on the remote SERVER. Transport only.

        Only non-None fields are sent. `error` is appended to the SERVER-side
        `errors` history by the tasks router (never a singular column).
        """
        if not task_id:
            raise RemoteNodeError(
                "Invalid task_id: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if result is not None:
            payload["result"] = result
        if progress_pct is not None:
            payload["progress_pct"] = progress_pct
        if error is not None:
            payload["error"] = error
        data = await self._request("PATCH", f"/api/tasks/{task_id}", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                f"Remote SERVER /api/tasks/{task_id} returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def _task_action(self, task_id: str, action: str) -> Dict[str, Any]:
        """POST /api/tasks/{task_id}/{action} on the remote SERVER."""
        if not task_id:
            raise RemoteNodeError(
                "Invalid task_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("POST", f"/api/tasks/{task_id}/{action}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                f"Remote SERVER /api/tasks/{task_id}/{action} returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """POST /api/tasks/{task_id}/cancel on the remote SERVER."""
        return await self._task_action(task_id, "cancel")

    async def pause_task(self, task_id: str) -> Dict[str, Any]:
        """POST /api/tasks/{task_id}/pause on the remote SERVER."""
        return await self._task_action(task_id, "pause")

    async def resume_task(self, task_id: str) -> Dict[str, Any]:
        """POST /api/tasks/{task_id}/resume on the remote SERVER."""
        return await self._task_action(task_id, "resume")

    async def execute_shared_tool(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /tools/execute on the remote SERVER.

        Always sends confirmed=False so the SERVER PolicyEngine remains the
        final authorization boundary. Never executes anything locally.
        """
        if not tool_name or not tool_name.isidentifier():
            raise RemoteNodeError(
                f"Invalid remote tool name: {tool_name!r}.",
                kind="client_error",
            )
        payload = {
            "tool_name": tool_name,
            "parameters": parameters or {},
            "confirmed": False,
        }
        data = await self._request("POST", "/tools/execute", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /tools/execute returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    # --- central conversations (transport only) ---

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        title: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /api/conversations/ on the remote SERVER."""
        if not conversation_id:
            raise RemoteNodeError(
                "Invalid conversation_id: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {"conversation_id": conversation_id}
        if title is not None:
            payload["title"] = title
        if device_id is not None:
            payload["device_id"] = device_id
        data = await self._request("POST", "/api/conversations/", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/conversations/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def list_conversations(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        """GET /api/conversations/ on the remote SERVER."""
        data = await self._request("GET", "/api/conversations/", params={"limit": limit})
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER /api/conversations/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """GET /api/conversations/{id} on the remote SERVER."""
        if not conversation_id:
            raise RemoteNodeError(
                "Invalid conversation_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("GET", f"/api/conversations/{conversation_id}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER conversation lookup returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def get_conversation_messages(
        self, conversation_id: str, *, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """GET /api/conversations/{id}/messages on the remote SERVER."""
        if not conversation_id:
            raise RemoteNodeError(
                "Invalid conversation_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request(
            "GET", f"/api/conversations/{conversation_id}/messages", params={"limit": limit},
        )
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER conversation messages returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def append_conversation_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        tool_calls_json: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /api/conversations/{id}/messages on the remote SERVER."""
        if not conversation_id:
            raise RemoteNodeError(
                "Invalid conversation_id: must be a non-empty string.",
                kind="client_error",
            )
        payload: Dict[str, Any] = {"role": role, "content": content}
        if tool_calls_json is not None:
            payload["tool_calls_json"] = tool_calls_json
        if tool_call_id is not None:
            payload["tool_call_id"] = tool_call_id
        if name is not None:
            payload["name"] = name
        data = await self._request(
            "POST", f"/api/conversations/{conversation_id}/messages", payload=payload,
        )
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER message append returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    # --- central memory (transport only) ---

    async def memory_set(self, *, key: str, value: Any, category: str = "general") -> Dict[str, Any]:
        """POST /api/memory/set on the remote SERVER."""
        if not key:
            raise RemoteNodeError(
                "Invalid key: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request(
            "POST", "/api/memory/set",
            payload={"key": key, "value": value, "category": category},
        )
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/memory/set returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def memory_get(self, key: str) -> Dict[str, Any]:
        """GET /api/memory/get/{key} on the remote SERVER."""
        if not key:
            raise RemoteNodeError(
                "Invalid key: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("GET", f"/api/memory/get/{key}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER memory lookup returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def memory_search(self, *, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """POST /api/memory/search on the remote SERVER."""
        data = await self._request(
            "POST", "/api/memory/search", payload={"query": query, "limit": limit},
        )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RemoteNodeError(
                "Remote SERVER /api/memory/search returned an unexpected payload.",
                kind="invalid_response",
            )
        return data["results"]

    async def memory_delete(self, key: str) -> Dict[str, Any]:
        """DELETE /api/memory/delete/{key} on the remote SERVER."""
        if not key:
            raise RemoteNodeError(
                "Invalid key: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("DELETE", f"/api/memory/delete/{key}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER memory delete returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    # --- central confirmations (transport only) ---

    async def confirmation_create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/confirmations/ on the remote SERVER."""
        if not isinstance(payload, dict) or not payload.get("confirmation_id"):
            raise RemoteNodeError(
                "Invalid confirmation payload: confirmation_id is required.",
                kind="client_error",
            )
        data = await self._request("POST", "/api/confirmations/", payload=payload)
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER /api/confirmations/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def confirmation_resolve(self, confirmation_id: str, *, approved: bool) -> Dict[str, Any]:
        """POST /api/confirmations/{id}/resolve on the remote SERVER."""
        if not confirmation_id:
            raise RemoteNodeError(
                "Invalid confirmation_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request(
            "POST", f"/api/confirmations/{confirmation_id}/resolve",
            payload={"approved": approved},
        )
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER confirmation resolve returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def confirmation_get(self, confirmation_id: str) -> Dict[str, Any]:
        """GET /api/confirmations/{id} on the remote SERVER."""
        if not confirmation_id:
            raise RemoteNodeError(
                "Invalid confirmation_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request("GET", f"/api/confirmations/{confirmation_id}")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER confirmation lookup returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def confirmation_consume(self, confirmation_id: str, *, session_id: str) -> Dict[str, Any]:
        """POST /api/confirmations/{id}/consume on the remote SERVER (atomic single-use)."""
        if not confirmation_id:
            raise RemoteNodeError(
                "Invalid confirmation_id: must be a non-empty string.",
                kind="client_error",
            )
        data = await self._request(
            "POST", f"/api/confirmations/{confirmation_id}/consume",
            payload={"session_id": session_id},
        )
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER confirmation consume returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def confirmations_pending(self) -> List[Dict[str, Any]]:
        """GET /api/confirmations/pending on the remote SERVER."""
        data = await self._request("GET", "/api/confirmations/pending")
        if not isinstance(data, list):
            raise RemoteNodeError(
                "Remote SERVER pending confirmations returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def confirmations_cleanup(self) -> Dict[str, Any]:
        """POST /api/confirmations/cleanup on the remote SERVER."""
        data = await self._request("POST", "/api/confirmations/cleanup")
        if not isinstance(data, dict):
            raise RemoteNodeError(
                "Remote SERVER confirmations cleanup returned an unexpected payload.",
                kind="invalid_response",
            )
        return data
