"""Home Assistant tools — SERVER-side only.

These tools run exclusively on the SERVER (registered only when
node_role == SERVER and home_assistant_enabled). The CORE never executes
them directly: it reaches them through remote_server_tool, which forwards
to the SERVER ToolRegistry/PolicyEngine via the existing bridge.

Reads are GREEN/SHARED; anything actuating devices is YELLOW/SHARED and
flows through the standard confirmation path. No shell, no subprocess,
no arbitrary URLs: the HA base URL comes only from SERVER configuration.
"""

import re
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

from core.config import get_settings
from core.contracts.enums import NodeRole, ParamKind, SecurityLevel, ToolVisibility
from core.contracts.tool import BaseTool, ToolResult
from core.home_assistant.client import HomeAssistantClient, HomeAssistantError
from core.logger import get_logger

logger = get_logger("jarvis.tools.home_assistant")

_MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

# Cap for list responses: HA instances can expose hundreds of entities and
# the full dump would destroy the LLM context window.
MAX_LIST_ENTITIES = 100
DEFAULT_LIST_ENTITIES = 30


def get_home_assistant_client() -> HomeAssistantClient:
    """Build a client from SERVER configuration (raises if unusable)."""
    settings = get_settings()
    return HomeAssistantClient(
        base_url=settings.home_assistant_url,
        token=settings.home_assistant_token,
        timeout=settings.home_assistant_timeout,
    )


def is_home_assistant_available() -> bool:
    """Whether this node may execute HA tools (SERVER role + enabled + configured)."""
    settings = get_settings()
    return (
        settings.node_role == NodeRole.SERVER
        and settings.home_assistant_enabled
        and get_home_assistant_client().is_configured
    )


def _ha_error(error: HomeAssistantError, level: SecurityLevel) -> ToolResult:
    # HomeAssistantError never carries the token by construction.
    return ToolResult.fail(error=str(error), security_level=level)


def _summarize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the fields useful to the LLM."""
    return {
        "entity_id": state.get("entity_id"),
        "state": state.get("state"),
        "attributes": state.get("attributes") or {},
        "last_changed": state.get("last_changed"),
        "last_updated": state.get("last_updated"),
    }


class GetStateArgs(BaseModel):
    entity_id: str = Field(..., description="HA entity_id, e.g. 'light.sala'")


class HomeAssistantGetStateTool(BaseTool):
    """Read the state of one Home Assistant entity (read-only)."""

    name: str = "home_assistant_get_state"
    description: str = "Read the current state of a Home Assistant entity (e.g. light.sala)."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = GetStateArgs
    param_kinds: Dict[str, ParamKind] = {"entity_id": ParamKind.IDENT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            state = await get_home_assistant_client().get_state(kwargs.get("entity_id", ""))
            return ToolResult.ok(data=_summarize_state(state), security_level=self.security_level)
        except HomeAssistantError as e:
            logger.error("HA get_state failed (%s): %s", e.kind, e.message)
            return _ha_error(e, self.security_level)


class GetStatesArgs(BaseModel):
    limit: int = Field(default=DEFAULT_LIST_ENTITIES, description="Max entities to return")


class HomeAssistantGetStatesTool(BaseTool):
    """List Home Assistant entity states (read-only, size-capped)."""

    name: str = "home_assistant_get_states"
    description: str = "List Home Assistant entity states (entity_id, state, attributes), capped for LLM context."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = GetStatesArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            limit = kwargs.get("limit", DEFAULT_LIST_ENTITIES)
            try:
                limit = max(1, min(int(limit), MAX_LIST_ENTITIES))
            except (TypeError, ValueError):
                limit = DEFAULT_LIST_ENTITIES
            states = await get_home_assistant_client().get_states()
            trimmed = [_summarize_state(s) for s in states[:limit]]
            return ToolResult.ok(
                data={"entities": trimmed, "returned": len(trimmed), "total": len(states)},
                security_level=self.security_level,
            )
        except HomeAssistantError as e:
            logger.error("HA get_states failed (%s): %s", e.kind, e.message)
            return _ha_error(e, self.security_level)


class CallServiceArgs(BaseModel):
    domain: str = Field(..., description="HA domain, e.g. 'light', 'scene', 'automation', 'script', 'switch'")
    service: str = Field(..., description="HA service, e.g. 'turn_on', 'turn_off', 'trigger'")
    service_data: Dict[str, Any] = Field(default_factory=dict, description="Structured JSON object payload")


class HomeAssistantCallServiceTool(BaseTool):
    """Execute a Home Assistant service (actuates devices — YELLOW).

    Covers lights, switches, scenes (scene.turn_on), automations
    (automation.trigger) and scripts (script.turn_on) through the same call.
    """

    name: str = "home_assistant_call_service"
    description: str = (
        "Execute a Home Assistant service (e.g. light.turn_on, scene.turn_on, "
        "automation.trigger). Controls real devices and requires confirmation."
    )
    security_level: SecurityLevel = SecurityLevel.YELLOW
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = CallServiceArgs
    param_kinds: Dict[str, ParamKind] = {"domain": ParamKind.IDENT, "service": ParamKind.IDENT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            result = await get_home_assistant_client().call_service(
                kwargs.get("domain", ""),
                kwargs.get("service", ""),
                kwargs.get("service_data") or {},
            )
            data = result if isinstance(result, (list, dict)) else {"result": result}
            return ToolResult.ok(data=data, security_level=self.security_level)
        except HomeAssistantError as e:
            logger.error("HA call_service failed (%s): %s", e.kind, e.message)
            return _ha_error(e, self.security_level)


class WakeOnLanArgs(BaseModel):
    mac: str = Field(..., description="Target MAC address, e.g. 'AA:BB:CC:DD:EE:FF'")
    broadcast_address: Optional[str] = Field(default=None, description="Broadcast address override")
    broadcast_port: Optional[int] = Field(default=None, description="Broadcast port override")


class HomeAssistantWakeOnLanTool(BaseTool):
    """Ask Home Assistant to send a magic packet (wake a configured machine)."""

    name: str = "home_assistant_wake_on_lan"
    description: str = "Send a Wake-on-LAN magic packet via Home Assistant to wake a machine."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = WakeOnLanArgs
    # MAC contains colons so it is not an IDENT; the strict AA:BB:... regex in
    # execute() is the real boundary (FREE_TEXT only skips shell rules here).
    param_kinds: Dict[str, ParamKind] = {
        "mac": ParamKind.FREE_TEXT,
        "broadcast_address": ParamKind.IDENT,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        mac = kwargs.get("mac", "")
        if not isinstance(mac, str) or not _MAC_REGEX.match(mac):
            return ToolResult.fail(
                error=f"Invalid MAC address: {mac!r}. Expected format AA:BB:CC:DD:EE:FF.",
                security_level=self.security_level,
            )
        service_data: Dict[str, Any] = {"mac": mac}
        if kwargs.get("broadcast_address"):
            service_data["broadcast_address"] = kwargs["broadcast_address"]
        if kwargs.get("broadcast_port") is not None:
            try:
                service_data["broadcast_port"] = int(kwargs["broadcast_port"])
            except (TypeError, ValueError):
                return ToolResult.fail(
                    error=f"Invalid broadcast_port: {kwargs['broadcast_port']!r}.",
                    security_level=self.security_level,
                )
        try:
            result = await get_home_assistant_client().call_service(
                "wake_on_lan", "send_magic_packet", service_data,
            )
            data = result if isinstance(result, (list, dict)) else {"result": result}
            return ToolResult.ok(data=data, security_level=self.security_level)
        except HomeAssistantError as e:
            logger.error("HA wake_on_lan failed (%s): %s", e.kind, e.message)
            return _ha_error(e, self.security_level)


def register_home_assistant_tools(registry) -> bool:
    """Register HA tools only on SERVER nodes with HA enabled and configured.

    Returns True when registered, False otherwise. Safe to call repeatedly.
    """
    if not is_home_assistant_available():
        return False
    registry.register(HomeAssistantGetStateTool())
    registry.register(HomeAssistantGetStatesTool())
    registry.register(HomeAssistantCallServiceTool())
    registry.register(HomeAssistantWakeOnLanTool())
    return True
