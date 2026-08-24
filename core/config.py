"""Centralized configuration management for JARVIS nodes using Pydantic Settings."""

import os
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.contracts.enums import NodeRole


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

    # Network Security — SSRF Protection
    net_allow_private_networks: List[str] = Field(
        default_factory=list,
        description="CIDR ranges allowed for fetch_url (SSRF guard). Default: all private/blocked.",
    )

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
