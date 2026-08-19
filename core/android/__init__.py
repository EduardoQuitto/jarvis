"""Android package — Android device communication stubs."""

from typing import Any, Dict, Optional
from core.logger import get_logger

logger = get_logger("jarvis.android")


class AndroidControllerStub:
    """Stub for Android device control via Termux API or ADB.

    Will control the Galaxy S20 FE and Galaxy Tab E.
    """

    def __init__(self, device_id: str = "android"):
        self._device_id = device_id
        logger.info("Android controller stub initialized for %s", device_id)

    async def send_notification(self, title: str, message: str) -> bool:
        """Send a notification to the Android device. STUB: returns False."""
        logger.warning("Android notification called but not implemented")
        return False

    async def get_battery_status(self) -> Dict[str, Any]:
        """Get battery status. STUB: returns placeholder."""
        return {"level": 0, "charging": False, "temperature": 0}

    async def get_contacts(self) -> list:
        """Get contacts. STUB: returns empty list."""
        return []

    async def send_sms(self, phone: str, message: str) -> bool:
        """Send SMS. STUB: returns False."""
        logger.warning("SMS send called but not implemented")
        return False

    async def make_call(self, phone: str) -> bool:
        """Make a phone call. STUB: returns False."""
        logger.warning("Call make called but not implemented")
        return False

    async def get_location(self) -> Dict[str, Any]:
        """Get device location. STUB: returns placeholder."""
        return {"lat": 0.0, "lon": 0.0, "accuracy": 0}

    async def take_photo(self) -> Optional[str]:
        """Take a photo. STUB: returns None."""
        return None
