"""Centralized configuration management for JARVIS nodes using Pydantic Settings."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.contracts.device import DeviceCapability, DeviceType
from core.contracts.enums import NodeRole


def validate_device_endpoint(value: str) -> str:
    """Validate and normalize a trusted device endpoint.

    Only an HTTP(S) origin is accepted: no credentials, path, query, fragment,
    or out-of-range port. The returned value never has a trailing slash.
    """
    if not isinstance(value, str):
        raise ValueError("endpoint must be a string")
    endpoint = value.strip()
    for ch in endpoint:
        if ord(ch) < 32:
            raise ValueError("endpoint contains invalid control characters")
    if not endpoint:
        raise ValueError("endpoint must not be empty")
    if "?" in endpoint or "#" in endpoint:
        raise ValueError("endpoint must not contain a query or fragment")

    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint contains an invalid host or port") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError("endpoint must use http or https")
    if not parsed.hostname:
        raise ValueError("endpoint must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint must not contain credentials")
    if parsed.path not in ("", "/"):
        raise ValueError("endpoint must not contain a path")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("endpoint port must be between 1 and 65535")
    return endpoint.rstrip("/")


def endpoint_host_port(endpoint: str) -> Tuple[str, int]:
    """Return host/port from an already validated trusted endpoint."""
    parsed = urlsplit(endpoint)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.hostname or "", port


class TrustedDeviceConfig(BaseModel):
    """SERVER-side descriptor for one explicitly provisioned device."""

    token: SecretStr = Field(..., description="Individual device token (secret)")
    device_type: DeviceType = Field(default=DeviceType.CORE, description="Authoritative device type")
    capabilities: List[DeviceCapability] = Field(
        default_factory=lambda: [DeviceCapability.LLM],
        description="Authoritative capabilities for this device",
    )
    endpoint: str = Field(..., description="Trusted compute endpoint (HTTP origin only)")

    @field_validator("token")
    @classmethod
    def _validate_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value().strip()
        if not token:
            raise ValueError("trusted device token must not be empty")
        return SecretStr(token)

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        return validate_device_endpoint(value)


class Settings(BaseSettings):
    """JARVIS System Settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Node Identity & Topology
    node_id: str = Field(default="node2-dev", description="Unique identifier of this node instance")
    node_role: NodeRole = Field(default=NodeRole.NODE2, description="Node role in the JARVIS topology")
    env: str = Field(default="development", description="Environment: development, test, production")
    debug: bool = Field(default=True, description="Enable debug logging and behavior")

    # Network & API
    host: str = Field(default="127.0.0.1", description="Host address to bind HTTP/WS server")
    port: int = Field(default=8000, description="Port to bind HTTP/WS server")
    api_key: str = Field(default="jarvis-dev-insecure-key-change-me", description="Shared API key for node authentication")

    # Remote node (CORE -> SERVER bridge). Empty server_url disables remote tools.
    server_url: str = Field(default="", description="Base URL of the remote JARVIS SERVER node")
    server_api_key: str = Field(default="", description="API key used to authenticate against the remote SERVER node")
    server_timeout: float = Field(default=30.0, description="Timeout in seconds for remote SERVER requests")

    device_token: Optional[SecretStr] = Field(
        default=None,
        description="Individual device token used for registration and heartbeat (CORE only)",
    )
    trusted_devices: Dict[str, TrustedDeviceConfig] = Field(
        default_factory=dict,
        description="SERVER-side trusted device descriptors (device_id -> descriptor)",
    )

    # Presence (CORE auto-registration + heartbeat on the SERVER).
    server_heartbeat_interval: float = Field(default=30.0, description="Interval in seconds between presence heartbeats")
    node_advertise_ip: Optional[str] = Field(default="", description="LAN IP announced to the SERVER (empty = not announced)")
    node_advertise_port: Optional[int] = Field(default=0, description="Port announced to the SERVER (0 = not announced)")

    # Central state (SERVER = source of truth, CORE = compute plane).
    # Disabled by default: local SQLite behavior is preserved for tests/dev.
    central_state_enabled: bool = Field(default=False, description="Route conversations/memory/confirmations through the SERVER")
    central_state_required: bool = Field(default=False, description="Fail explicitly when central state is unreachable (no local fallback)")

    # Security & Policy Settings
    allowlist_enabled: bool = Field(default=True, description="Enforce strict allowlist on actions and apps")
    confirm_yellow_actions: bool = Field(default=True, description="Require confirmation before executing yellow actions")
    confirm_red_actions: bool = Field(default=True, description="Require explicit token/auth for red actions")

    # Storage & Persistence
    db_path: str = Field(default="./data/jarvis.db", description="Path to SQLite database file")

    # LLM Configuration
    llm_provider: str = Field(default="ollama", description="LLM provider: ollama, openai, mock")
    llm_model: str = Field(default="qwen2.5:7b", description="Model name to use")
    llm_base_url: str = Field(default="http://localhost:11434", description="LLM API base URL")
    llm_api_key: str = Field(default="", description="API key for cloud LLM providers")
    llm_max_tokens: int = Field(default=4096, description="Max tokens for LLM responses")
    llm_temperature: float = Field(default=0.7, description="LLM temperature")
    llm_timeout: float = Field(default=120.0, description="LLM request timeout in seconds")

    # Ollama-specific
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(default="qwen2.5:7b", description="Ollama model name")

    # External LLM Provider (OpenAI-compatible: Groq, Together, OpenRouter, Gemini)
    external_llm_api_key: str = Field(default="", description="API key for external LLM provider")
    external_llm_base_url: str = Field(default="", description="Base URL for external LLM API")
    external_llm_model: str = Field(default="", description="Model name for external LLM provider")
    external_llm_provider: str = Field(default="", description="Descriptive name for external provider")

    # Google AI Studio (Gemini) cloud fallback — OpenAI-compatible endpoint.
    # Empty api_key disables the Google slot in the router.
    google_api_key: str = Field(default="", description="API key for Google AI Studio")
    google_model: str = Field(default="gemini-3.7-flash", description="Gemini model name")
    google_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Google AI Studio OpenAI-compatible base URL",
    )

    # Home Assistant (SERVER-side only: the token must never reach the CORE).
    # Disabled by default: tools stay unregistered and the system is unaffected.
    home_assistant_enabled: bool = Field(default=False, description="Enable Home Assistant integration on this node")
    home_assistant_url: str = Field(default="", description="Home Assistant base URL (e.g. http://homeassistant.local:8123)")
    home_assistant_token: str = Field(default="", description="Home Assistant Long-Lived Access Token (SERVER only)")
    home_assistant_timeout: float = Field(default=10.0, description="Timeout in seconds for Home Assistant requests")

    # Notifications (Phase 15.1) — destinations come only from settings.
    # No addresses/URLs are ever accepted from tools or the LLM.
    notification_webhook_url: str = Field(default="", description="Configured webhook destination for notifications (empty = unavailable)")

    # Network Security — SSRF Protection
    net_allow_private_networks: List[str] = Field(
        default_factory=list,
        description="CIDR ranges allowed for fetch_url (SSRF guard). Default: all private/blocked.",
    )

    # CORS
    cors_origins: List[str] = Field(
        default_factory=list,
        description="Allowed CORS origins. Empty list = same-origin only (production). "
                    "For development, set JARVIS_CORS_ORIGINS='[\"http://localhost:3000\"]'.",
    )

    # Context Architecture (Phase 15.2)
    context_budget_enabled: bool = Field(default=True, description="Enable context budget management")
    context_max_tokens: int = Field(default=8192, description="Maximum total tokens for LLM context (prompt + completion)")
    context_response_reserve: int = Field(default=1024, description="Tokens reserved for LLM response")
    context_compact_threshold: float = Field(default=0.7, description="Trigger compaction when context exceeds this fraction of budget")
    context_compact_keep_recent: int = Field(default=10, description="Number of recent messages to preserve verbatim during compaction")
    tool_selection_enabled: bool = Field(default=True, description="Enable deterministic tool context selection")
    tool_selection_min_tools: int = Field(default=3, description="Minimum tools to always include in selection")
    tool_selection_max_tools: int = Field(default=15, description="Maximum tools to send to the LLM")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Default Allowed Applications (Can be extended via environment or config)
    allowed_apps: Dict[str, str] = Field(
        default_factory=lambda: {
            "notepad": "notepad.exe",
            "calc": "calc.exe",
            "vscode": "code.exe",
            "unity": "Unity.exe",
            "terminal": "powershell.exe",
        },
        description="Safe friendly name to executable mapping",
    )

    # Allowed Base Directories for File Operations
    allowed_paths: List[str] = Field(
        default_factory=lambda: [
            str(Path.home()),
            os.path.abspath("."),
        ],
        description="List of filesystem paths accessible by file tools",
    )

    @model_validator(mode="after")
    def _validate_trusted_devices(self) -> "Settings":
        seen_tokens: Dict[str, str] = {}
        for device_id, descriptor in self.trusted_devices.items():
            if not device_id.strip():
                raise ValueError("trusted device IDs must not be empty")
            token = descriptor.token.get_secret_value()
            if token in seen_tokens:
                raise ValueError(
                    "trusted devices must use distinct tokens "
                    f"({seen_tokens[token]!r} and {device_id!r})"
                )
            seen_tokens[token] = device_id
        return self

    @property
    def is_production(self) -> bool:
        """Helper to determine if running in production mode."""
        return self.env.lower() == "production"


# Singleton instance accessor
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Retrieve global settings instance or initialize from environment."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset global settings (useful for tests)."""
    global _settings
    _settings = None
