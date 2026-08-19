"""Contracts for Device registry and distributed system state."""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    """Status of a device/node in the distributed system."""
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    ONLINE = "ONLINE"
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class DeviceType(str, Enum):
    """Type of device in the JARVIS topology."""
    SERVER = "SERVER"
    CORE = "CORE"
    NODE2 = "NODE2"
    MOBILE = "MOBILE"
    PANEL = "PANEL"
    UNKNOWN = "UNKNOWN"


class DeviceCapability(str, Enum):
    """Capabilities a device can provide."""
    LLM = "llm"
    VISION = "vision"
    STT = "stt"
    TTS = "tts"
    WAKE_WORD = "wake_word"
    WINDOWS_AUTOMATION = "windows_automation"
    ANDROID = "android"
    HOME_ASSISTANT = "home_assistant"
    VOIP = "voip"
    NOTIFICATIONS = "notifications"
    SENSOR = "sensor"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    DISPLAY = "display"
    MCP = "mcp"


class Device(BaseModel):
    """A registered device in the JARVIS network."""
    device_id: str = Field(..., description="Unique device identifier")
    name: str = Field(default="", description="Human-readable device name")
    device_type: DeviceType = Field(default=DeviceType.UNKNOWN)
    status: NodeStatus = Field(default=NodeStatus.OFFLINE)
    capabilities: List[DeviceCapability] = Field(default_factory=list)
    version: str = Field(default="0.1.0", description="Software version on the device")
    ip_address: Optional[str] = Field(default=None)
    port: Optional[int] = Field(default=None)
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra device info")


class DeviceRegistrationRequest(BaseModel):
    """Request to register or update a device."""
    device_id: str = Field(..., description="Unique device identifier")
    name: str = Field(default="")
    device_type: DeviceType = Field(default=DeviceType.UNKNOWN)
    capabilities: List[DeviceCapability] = Field(default_factory=list)
    version: str = Field(default="0.1.0")
    ip_address: Optional[str] = None
    port: Optional[int] = None


class DeviceHeartbeat(BaseModel):
    """Heartbeat payload from a device."""
    device_id: str
    status: NodeStatus = Field(default=NodeStatus.ONLINE)
    capabilities: List[DeviceCapability] = Field(default_factory=list)
