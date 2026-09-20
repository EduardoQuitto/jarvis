"""CORE presence: auto-registration + periodic heartbeat on the SERVER.

Infrastructure only — NOT an LLM tool. The LLM can neither control the
heartbeat nor change network configuration.

Behavior:
- Registers this node via POST /api/devices/, then heartbeats via
  POST /api/devices/heartbeat every `server_heartbeat_interval` seconds.
- SERVER offline: logs a warning, keeps the Core fully functional
  (Ollama + local tools), retries on the next cycle. Never raises into
  the main process.
- SERVER back: re-registers if needed, resumes heartbeats normally.
- No aggressive retry: at most one attempt per configured interval.
"""

import asyncio
from typing import List, Optional

from core.config import get_settings
from core.contracts.device import DeviceCapability, DeviceType
from core.logger import get_logger
from core.network.node_client import RemoteNodeClient, RemoteNodeError

logger = get_logger("jarvis.network.presence")

CORE_DISPLAY_NAME = "J.A.R.V.I.S. Core - i5-14400"


def project_version() -> str:
    """Project version from the installed package metadata, with fallbacks."""
    try:
        from importlib.metadata import version
        return version("jarvis")
    except Exception:
        try:
            from core import __version__ as fallback
            return fallback
        except Exception:
            return "0.0.0"


class NodePresenceManager:
    """Keeps this node's registration + heartbeat alive on the remote SERVER."""

    def __init__(
        self,
        *,
        client: RemoteNodeClient,
        device_id: str,
        name: str = CORE_DISPLAY_NAME,
        device_type: str = DeviceType.CORE.value,
        capabilities: Optional[List[str]] = None,
        version: Optional[str] = None,
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
        interval: float = 30.0,
    ):
        self._client = client
        self._device_id = device_id
        self._name = name
        self._device_type = device_type
        self._capabilities = capabilities if capabilities is not None else [DeviceCapability.LLM.value]
        self._version = version or project_version()
        self._ip_address = ip_address
        self._port = port if port and port > 0 else None
        self._interval = interval if interval and interval > 0 else 30.0
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._registered = False

    @classmethod
    def from_settings(cls, settings=None, client: Optional[RemoteNodeClient] = None) -> Optional["NodePresenceManager"]:
        """Build from settings, or None when no SERVER URL is configured.

        Never invents an inbound endpoint: ip/port are only announced when
        JARVIS_NODE_ADVERTISE_IP / JARVIS_NODE_ADVERTISE_PORT are set.
        """
        settings = settings or get_settings()
        if not settings.server_url:
            return None
        ip = settings.node_advertise_ip or None
        raw_port = settings.node_advertise_port or 0
        return cls(
            client=client or RemoteNodeClient(
                base_url=settings.server_url,
                api_key=settings.server_api_key,
                timeout=settings.server_timeout,
            ),
            device_id=settings.node_id,
            name=CORE_DISPLAY_NAME,
            device_type=DeviceType.CORE.value,
            capabilities=[DeviceCapability.LLM.value],
            version=project_version(),
            ip_address=ip,
            port=raw_port if raw_port > 0 else None,
            interval=settings.server_heartbeat_interval,
        )

    @property
    def is_running(self) -> bool:
        """Whether the background presence task is active."""
        return self._task is not None and not self._task.done()

    @property
    def is_registered(self) -> bool:
        """Whether the last registration/heartbeat cycle succeeded."""
        return self._registered

    async def start(self) -> None:
        """Spawn the background presence task. Returns immediately (non-blocking)."""
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="jarvis-presence")

    async def stop(self) -> None:
        """Cancel the background task and wait for it. Never raises."""
        self._stop.set()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Presence shutdown swallowed error: %s", str(e))

    async def register_once(self) -> bool:
        """Single registration attempt. Returns success, never raises."""
        try:
            await self._client.register_device(
                device_id=self._device_id,
                name=self._name,
                device_type=self._device_type,
                capabilities=self._capabilities,
                version=self._version,
                ip_address=self._ip_address,
                port=self._port,
            )
            if not self._registered:
                logger.info("Presence: registered '%s' on remote SERVER.", self._device_id)
            self._registered = True
            return True
        except RemoteNodeError as e:
            logger.warning("Presence: SERVER unreachable (%s): %s", e.kind, e.message)
            self._registered = False
            return False
        except Exception as e:  # defensive: never let presence kill the Core
            logger.warning("Presence: unexpected registration error: %s", str(e))
            self._registered = False
            return False

    async def heartbeat_once(self) -> bool:
        """Single heartbeat attempt. Returns success, never raises."""
        try:
            await self._client.heartbeat(
                device_id=self._device_id,
                status="ONLINE",
                capabilities=self._capabilities,
            )
            return True
        except RemoteNodeError as e:
            logger.warning("Presence: heartbeat failed (%s): %s", e.kind, e.message)
            return False
        except Exception as e:  # defensive: never let presence kill the Core
            logger.warning("Presence: unexpected heartbeat error: %s", str(e))
            return False

    async def _run(self) -> None:
        """Background loop: register, then heartbeat each interval."""
        await self.register_once()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            if self._registered:
                if not await self.heartbeat_once():
                    # SERVER may have restarted: re-register next cycle.
                    self._registered = False
            else:
                await self.register_once()
