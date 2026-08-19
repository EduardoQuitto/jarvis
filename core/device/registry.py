"""Device Registry — manages device registration, status, and capability discovery."""

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.contracts.device import (
    Device,
    DeviceRegistrationRequest,
    DeviceHeartbeat,
    NodeStatus,
    DeviceType,
    DeviceCapability,
)
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger

logger = get_logger("jarvis.device_registry")

HEARTBEAT_TIMEOUT_SECONDS = 120


class DeviceRegistry:
    """Manages device registration, heartbeats, and status tracking."""

    def __init__(self, memory: Optional[SQLiteMemoryProvider] = None):
        self._memory = memory

    def _get_memory(self) -> SQLiteMemoryProvider:
        if self._memory is None:
            self._memory = SQLiteMemoryProvider()
        return self._memory

    async def register_device(self, request: DeviceRegistrationRequest) -> Device:
        """Register or update a device."""
        mem = self._get_memory()
        await mem.register_device(
            device_id=request.device_id,
            name=request.name,
            device_type=request.device_type.value,
            status=NodeStatus.ONLINE.value,
            capabilities=json.dumps([c.value for c in request.capabilities]),
            version=request.version,
            ip_address=request.ip_address or "",
            port=request.port or 0,
            metadata="{}",
        )
        logger.info("Registered device: %s (%s)", request.device_id, request.device_type.value)

        await get_event_bus().publish(SystemEvent(
            event_type=EventType.DEVICE_ONLINE,
            source="device_registry",
            data={"device_id": request.device_id, "device_type": request.device_type.value},
        ))

        return await self.get_device(request.device_id)

    async def update_heartbeat(self, heartbeat: DeviceHeartbeat) -> None:
        """Update device heartbeat."""
        mem = self._get_memory()
        status_str = heartbeat.status.value
        await mem.update_device_heartbeat(
            device_id=heartbeat.device_id,
            status=status_str,
        )
        logger.debug("Heartbeat from %s: %s", heartbeat.device_id, status_str)

    async def get_device(self, device_id: str) -> Optional[Device]:
        """Get a device by ID."""
        mem = self._get_memory()
        row = await mem.get_device(device_id)
        if not row:
            return None
        return self._row_to_device(row)

    async def list_devices(self, device_type: Optional[DeviceType] = None) -> List[Device]:
        """List all devices."""
        mem = self._get_memory()
        rows = await mem.list_devices()
        devices = [self._row_to_device(r) for r in rows]
        if device_type:
            devices = [d for d in devices if d.device_type == device_type]
        return devices

    async def get_online_devices(self) -> List[Device]:
        """Get all devices that have sent a recent heartbeat."""
        all_devices = await self.list_devices()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
        online = []
        for d in all_devices:
            last_seen = d.last_seen
            if isinstance(last_seen, str):
                try:
                    last_seen = datetime.fromisoformat(last_seen)
                except (ValueError, TypeError):
                    continue
            if last_seen and last_seen > cutoff:
                online.append(d)
        return online

    async def remove_device(self, device_id: str) -> bool:
        """Remove a device from the registry."""
        logger.info("Removed device: %s", device_id)
        await get_event_bus().publish(SystemEvent(
            event_type=EventType.DEVICE_OFFLINE,
            source="device_registry",
            data={"device_id": device_id},
        ))
        return True

    def _row_to_device(self, row: Dict[str, Any]) -> Device:
        """Convert a database row to a Device model."""
        try:
            capabilities_raw = json.loads(row.get("capabilities", "[]"))
            capabilities = [DeviceCapability(c) for c in capabilities_raw if isinstance(c, str)]
        except (json.JSONDecodeError, ValueError):
            capabilities = []

        try:
            last_seen = datetime.fromisoformat(row["last_seen"]) if row.get("last_seen") else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            last_seen = datetime.now(timezone.utc)

        return Device(
            device_id=row["device_id"],
            device_type=DeviceType(row.get("device_type", "UNKNOWN")),
            name=row.get("name", ""),
            capabilities=capabilities,
            ip_address=row.get("ip_address"),
            port=row.get("port"),
            status=NodeStatus(row.get("status", "OFFLINE")),
            last_seen=last_seen,
            version=row.get("version", "0.1.0"),
            metadata=json.loads(row.get("metadata", "{}")),
        )
