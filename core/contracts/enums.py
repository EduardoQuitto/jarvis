"""Core enumerations and status definitions for JARVIS."""

from enum import Enum


class NodeRole(str, Enum):
    """Hardware node roles within the distributed JARVIS network."""
    SERVER = "SERVER"       # JARVIS Server: i3-3220, Ubuntu Server, HA, Central State
    CORE = "CORE"           # JARVIS Core: i5-14400, LLM, Vision, Heavy Tasks
    NODE2 = "NODE2"         # Aux Node: Pentium G3260, Dev/Lab/Tasks
    MOBILE = "MOBILE"       # Galaxy S20 FE, Mobile sensor/voice node
    PANEL = "PANEL"         # Galaxy Tab E, Lightweight telemetry dashboard


class SecurityLevel(str, Enum):
    """Security classification levels as defined in AGENTS.md."""
    GREEN = "GREEN"         # Automatically allowed: telemetry, read metrics, authorized apps
    YELLOW = "YELLOW"       # Requires confirmation: restart, shutdown, modify settings, kill apps
    RED = "RED"             # Requires explicit authorization: delete data, arbitrary code, firewall


class TaskStatus(str, Enum):
    """Execution status for tasks and planner steps."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    CANCELLED = "CANCELLED"


class ToolVisibility(str, Enum):
    """Controls which LLM providers can see a tool's schema.

    LOCAL_ONLY — only providers flagged as local (Ollama, Mock) receive this tool.
    SHARED     — visible to all providers, including external/cloud.
    """
    LOCAL_ONLY = "LOCAL_ONLY"
    SHARED = "SHARED"
