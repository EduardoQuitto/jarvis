"""Home Assistant integration stubs."""

from typing import Any, Dict, List, Optional
from core.logger import get_logger

logger = get_logger("jarvis.hass")


class HomeAssistantStub:
    """Stub for Home Assistant integration.

    Will connect to HASS via REST API/WebSocket for smart home control.
    """

    def __init__(self, base_url: str = "http://localhost:8123", token: str = ""):
        self._base_url = base_url
        self._token = token
        self._connected = False
        logger.info("Home Assistant stub initialized (url=%s)", base_url)

    async def connect(self) -> bool:
        """Connect to Home Assistant. STUB: returns False."""
        logger.warning("HASS connect called but not implemented")
        return False

    async def get_states(self) -> List[Dict[str, Any]]:
        """Get all entity states. STUB: returns empty list."""
        return []

    async def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get state of a specific entity. STUB: returns None."""
        return None

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Call a Home Assistant service. STUB: returns False."""
        logger.warning("HASS service call called but not implemented: %s.%s", domain, service)
        return False

    async def turn_on(self, entity_id: str) -> bool:
        """Turn on an entity. STUB: returns False."""
        return await self.call_service("homeassistant", "turn_on", entity_id)

    async def turn_off(self, entity_id: str) -> bool:
        """Turn off an entity. STUB: returns False."""
        return await self.call_service("homeassistant", "turn_off", entity_id)

    async def toggle(self, entity_id: str) -> bool:
        """Toggle an entity. STUB: returns False."""
        return await self.call_service("homeassistant", "toggle", entity_id)

    async def set_light(self, entity_id: str, brightness: int = 255, color_temp: int = 4000) -> bool:
        """Set light properties. STUB: returns False."""
        data = {"brightness": brightness, "color_temp": color_temp}
        return await self.call_service("light", "turn_on", entity_id, data)

    async def set_climate(self, entity_id: str, temperature: float) -> bool:
        """Set climate/thermostat. STUB: returns False."""
        data = {"temperature": temperature}
        return await self.call_service("climate", "set_temperature", entity_id, data)

    async def get_automations(self) -> List[Dict[str, Any]]:
        """Get available automations. STUB: returns empty list."""
        return []
