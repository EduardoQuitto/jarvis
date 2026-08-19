"""Capability Router — routes tasks to devices based on capabilities."""

from typing import Any, Dict, List, Optional

from core.contracts.device import Device, DeviceType, DeviceCapability
from core.device.registry import DeviceRegistry
from core.logger import get_logger

logger = get_logger("jarvis.capability_router")


class CapabilityRouter:
    """Routes tasks to the best device based on required capabilities.

    This enables distributed execution — tasks can be routed to
    MOBILE for voice, SERVER for compute, or CORE for LLM.
    """

    def __init__(self, registry: Optional[DeviceRegistry] = None):
        self._registry = registry or DeviceRegistry()

    async def find_device_for_capabilities(
        self,
        required_capabilities: List[str],
        prefer_online: bool = True,
        device_type: Optional[DeviceType] = None,
    ) -> Optional[Device]:
        """Find the best device that has all required capabilities."""
        devices = await self._registry.list_devices()

        if prefer_online:
            devices = [d for d in devices if d.status in ("ONLINE", "BUSY")]

        if device_type:
            devices = [d for d in devices if d.device_type == device_type]

        required_set = set(required_capabilities)

        for device in devices:
            # Convert DeviceCapability enums to strings for comparison
            device_caps = set(c.value if hasattr(c, "value") else c for c in device.capabilities)
            if required_set.issubset(device_caps):
                logger.info(
                    "Routed capabilities %s to device %s (%s)",
                    required_capabilities,
                    device.device_id,
                    device.device_type.value,
                )
                return device

        logger.warning("No device found for capabilities: %s", required_capabilities)
        return None

    async def get_device_for_task(self, task_type: str) -> Optional[Device]:
        """Route a task type to the appropriate device."""
        task_device_map = {
            "voice": [DeviceType.MOBILE, DeviceType.CORE],
            "vision": [DeviceType.CORE],
            "llm": [DeviceType.CORE],
            "compute": [DeviceType.SERVER],
            "storage": [DeviceType.SERVER],
            "ui": [DeviceType.MOBILE, DeviceType.PANEL],
            "hass": [DeviceType.SERVER],
        }

        preferred_types = task_device_map.get(task_type, [DeviceType.CORE, DeviceType.SERVER])

        for device_type in preferred_types:
            device = await self._registry.get_online_devices()
            for d in device:
                if d.device_type == device_type:
                    return d

        # Fallback to any online device
        online = await self._registry.get_online_devices()
        return online[0] if online else None

    async def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of all device capabilities."""
        devices = await self._registry.list_devices()
        summary = {
            "total_devices": len(devices),
            "online": len([d for d in devices if d.status in ("ONLINE", "BUSY")]),
            "by_type": {},
            "capabilities": {},
        }

        for device in devices:
            dtype = device.device_type.value
            summary["by_type"][dtype] = summary["by_type"].get(dtype, 0) + 1

            for cap in device.capabilities:
                summary["capabilities"][cap] = summary["capabilities"].get(cap, 0) + 1

        return summary
