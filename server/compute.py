"""Compute-plane helpers for the SERVER gateway (Phase 12).

- select_compute_node(): pick one ONLINE/READY CORE with LLM capability
  from the DeviceRegistry. V1 semantics: first match wins; the code is
  structured so smarter selection can replace it later (no balancing now).
- forward_chat_send / forward_chat_stream(): forward an authenticated chat
  request to the selected CORE internal endpoint and return/relay the result.

No queue, no scheduler, no workers. Timeouts reuse the LLM budget.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from core.config import get_settings
from core.contracts.device import Device, DeviceCapability, DeviceType, NodeStatus
from core.device.registry import DeviceRegistry
from core.logger import get_logger

logger = get_logger("jarvis.server.compute")


class ComputeUnavailable(Exception):
    """Explicit error: no usable compute CORE (never a faked response)."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


_registry: Optional[DeviceRegistry] = None


def _get_registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
    return _registry


def reset_compute_registry() -> None:
    """Reset the gateway registry cache (used by tests)."""
    global _registry
    _registry = None


def _capability_values(device: Device) -> List[str]:
    values = []
    for capability in device.capabilities or []:
        values.append(capability.value if hasattr(capability, "value") else str(capability))
    return values


def is_compute_eligible(device: Device) -> bool:
    """A CORE is eligible when ONLINE/READY, LLM-capable and addressable."""
    if device.device_type != DeviceType.CORE:
        return False
    if device.status not in (NodeStatus.ONLINE, NodeStatus.READY):
        return False
    if DeviceCapability.LLM.value not in _capability_values(device):
        return False
    if not device.ip_address:
        return False
    try:
        if not device.port or int(device.port) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    return True


async def select_compute_node() -> Optional[Device]:
    """Return one eligible compute CORE, or None when unavailable."""
    registry = _get_registry()
    try:
        online = await registry.get_online_devices()
    except Exception as e:
        logger.error("Compute discovery failed: %s", str(e))
        return None
    eligible = [d for d in online if is_compute_eligible(d)]
    if not eligible:
        return None
    node = eligible[0]
    logger.info("Selected compute node: %s (%s:%s)", node.device_id, node.ip_address, node.port)
    return node


def compute_base_url(device: Device) -> str:
    """HTTP base URL of a compute node (no secrets involved)."""
    return f"http://{device.ip_address}:{int(device.port)}"


def _forward_headers() -> Dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def _forward_timeout() -> float:
    return get_settings().llm_timeout


async def forward_chat_send(
    payload: Dict[str, Any], node: Optional[Device] = None,
) -> Dict[str, Any]:
    """Forward POST /api/chat/send to the selected CORE. Raises on failure."""
    node = node or await select_compute_node()
    if node is None:
        raise ComputeUnavailable("No eligible compute CORE is online.")
    url = f"{compute_base_url(node)}/internal/chat/send"
    try:
        async with httpx.AsyncClient(timeout=_forward_timeout()) as client:
            response = await client.post(url, headers=_forward_headers(), json=payload)
    except httpx.TimeoutException as e:
        raise ComputeUnavailable(f"Compute node timed out: {e}") from e
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise ComputeUnavailable(f"Compute node unreachable: {e}") from e
    if response.status_code >= 400:
        raise ComputeUnavailable(
            f"Compute node returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )
    try:
        return response.json()
    except Exception as e:
        raise ComputeUnavailable(f"Compute node returned invalid JSON: {e}") from e


async def forward_chat_stream(
    payload: Dict[str, Any], node: Optional[Device] = None,
) -> AsyncGenerator[bytes, None]:
    """Forward POST /internal/chat/stream, relaying raw SSE bytes untouched.

    The generator owns the upstream connection: breaking out closes it via
    aclose, so client disconnects leave no orphan upstream connection.
    Raises ComputeUnavailable before the first byte when no CORE is online;
    mid-stream transport failures propagate to the caller.
    """
    node = node or await select_compute_node()
    if node is None:
        raise ComputeUnavailable("No eligible compute CORE is online.")
    url = f"{compute_base_url(node)}/internal/chat/stream"
    try:
        async with httpx.AsyncClient(timeout=_forward_timeout()) as client:
            async with client.stream("POST", url, headers=_forward_headers(), json=payload) as response:
                if response.status_code >= 400:
                    raise ComputeUnavailable(
                        f"Compute node returned HTTP {response.status_code}.",
                        status_code=response.status_code,
                    )
                async for chunk in response.aiter_bytes():
                    yield chunk
    except ComputeUnavailable:
        raise
    except httpx.TimeoutException as e:
        raise ComputeUnavailable(f"Compute node stream timed out: {e}") from e
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise ComputeUnavailable(f"Compute node stream unreachable: {e}") from e
