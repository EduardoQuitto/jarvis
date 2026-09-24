"""Async Home Assistant REST client (SERVER-side only).

Speaks the Home Assistant HTTP API with a Long-Lived Access Token that never
leaves the SERVER process: the token is used here for the Authorization
header and is never included in errors, logs or payloads.

Transport only: one generic _request() plus typed methods. A future
WebSocket/EventBus subscription layer can reuse _build_client()/_build_headers()
without rewriting this module (REST remains sufficient for this phase).
"""

import re
from typing import Any, Dict, List, Optional

import httpx

from core.logger import get_logger

logger = get_logger("jarvis.home_assistant")

# HA entity/domain/service names: lowercase segments separated by dots/underscores.
# Slightly narrower than the generic IDENT kind on purpose (no uppercase, no dash).
_HA_NAME_REGEX = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


class HomeAssistantError(Exception):
    """Standardized error for Home Assistant communication failures.

    The token is never embedded in message/details — only kind, status and
    a redacted upstream body excerpt.
    """

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


def validate_ha_name(value: str, what: str = "name") -> str:
    """Validate an HA entity_id/domain/service name (raises HomeAssistantError)."""
    if not isinstance(value, str) or not _HA_NAME_REGEX.match(value):
        raise HomeAssistantError(
            f"Invalid Home Assistant {what}: {value!r}.",
            kind="client_error",
        )
    return value


class HomeAssistantClient:
    """Async client for one Home Assistant instance.

    Args:
        base_url: HA base URL (e.g. http://homeassistant.local:8123).
        token: Long-Lived Access Token (SERVER configuration only).
        timeout: Per-request timeout in seconds.
        transport: Optional httpx transport (tests use MockTransport).
    """

    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._token = token or ""
        self.timeout = timeout
        self._transport = transport

    @property
    def is_configured(self) -> bool:
        """Whether URL and token are both present."""
        return bool(self.base_url and self._token)

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._build_headers(),
            transport=self._transport,
        )

    async def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform one HTTP request and return the parsed JSON body."""
        if not self.base_url:
            raise HomeAssistantError(
                "Home Assistant is not configured (URL is empty).",
                kind="configuration",
            )
        if not self._token:
            raise HomeAssistantError(
                "Home Assistant is not configured (token is empty).",
                kind="configuration",
            )
        url = f"{self.base_url}{path}"
        try:
            async with self._build_client() as client:
                response = await client.request(method, url, json=payload)
        except httpx.TimeoutException as e:
            logger.error("Home Assistant timeout (%s %s): %s", method, path, str(e))
            raise HomeAssistantError(
                f"Home Assistant request timed out after {self.timeout}s: {method} {path}",
                kind="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.error("Home Assistant connection refused (%s %s): %s", method, path, str(e))
            raise HomeAssistantError(
                f"Home Assistant connection refused at {self.base_url}.",
                kind="connection",
            ) from e
        except httpx.NetworkError as e:
            logger.error("Home Assistant network error (%s %s): %s", method, path, str(e))
            raise HomeAssistantError(
                f"Home Assistant network error: {e}",
                kind="connection",
            ) from e
        except HomeAssistantError:
            raise
        except Exception as e:
            logger.error("Home Assistant transport error (%s %s): %s", method, path, str(e))
            raise HomeAssistantError(
                f"Home Assistant transport error: {e}",
                kind="connection",
            ) from e

        status = response.status_code
        if status in (401, 403):
            raise HomeAssistantError(
                f"Home Assistant authentication failed (HTTP {status}).",
                kind="auth",
                status_code=status,
            )
        if status == 404:
            raise HomeAssistantError(
                f"Home Assistant resource not found (HTTP 404): {method} {path}.",
                kind="not_found",
                status_code=status,
            )
        if status == 429:
            raise HomeAssistantError(
                "Home Assistant rate limit exceeded (HTTP 429).",
                kind="rate_limited",
                status_code=status,
            )
        if 400 <= status < 500:
            raise HomeAssistantError(
                f"Home Assistant rejected the request (HTTP {status}).",
                kind="client_error",
                status_code=status,
            )
        if status >= 500:
            raise HomeAssistantError(
                f"Home Assistant server error (HTTP {status}).",
                kind="server_error",
                status_code=status,
            )

        try:
            return response.json()
        except Exception as e:
            raise HomeAssistantError(
                f"Home Assistant returned invalid JSON for {method} {path}.",
                kind="invalid_response",
                status_code=status,
            ) from e

    async def health(self) -> Dict[str, Any]:
        """GET /api/ — HA answers {"message": "API running."} when healthy."""
        data = await self._request("GET", "/api/")
        if not isinstance(data, dict):
            raise HomeAssistantError(
                "Home Assistant /api/ returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        """GET /api/states/{entity_id}."""
        validate_ha_name(entity_id, "entity_id")
        data = await self._request("GET", f"/api/states/{entity_id}")
        if not isinstance(data, dict):
            raise HomeAssistantError(
                f"Home Assistant state for {entity_id} has an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def get_states(self) -> List[Dict[str, Any]]:
        """GET /api/states — full state list (callers must trim for the LLM)."""
        data = await self._request("GET", "/api/states")
        if not isinstance(data, list):
            raise HomeAssistantError(
                "Home Assistant /api/states returned an unexpected payload.",
                kind="invalid_response",
            )
        return data

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """POST /api/services/{domain}/{service} with a JSON object payload."""
        validate_ha_name(domain, "domain")
        validate_ha_name(service, "service")
        # service_data comes from the LLM: enforce a plain JSON object so no
        # string payload can smuggle shell/host/URL semantics anywhere.
        if service_data is None:
            service_data = {}
        if not isinstance(service_data, dict):
            raise HomeAssistantError(
                "Home Assistant service_data must be a JSON object.",
                kind="client_error",
            )
        return await self._request(
            "POST", f"/api/services/{domain}/{service}", payload=service_data,
        )
