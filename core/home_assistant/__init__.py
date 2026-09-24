"""Home Assistant integration (SERVER-side only).

The Long-Lived Access Token lives exclusively in the SERVER configuration.
The CORE never receives it: remote access flows through remote_server_tool,
which executes these tools on the SERVER via the existing bridge.
"""

from core.home_assistant.client import HomeAssistantClient, HomeAssistantError

__all__ = ["HomeAssistantClient", "HomeAssistantError"]
