"""Windows Agent lifecycle and node coordinator."""

from typing import Any, Dict, Optional
from core.config import Settings, get_settings
from core.contracts.enums import NodeRole
from tools.registry import ToolRegistry, get_tool_registry
from tools import register_default_tools
from windows_agent.system import WindowsSystemCollector
from windows_agent.manager import WindowsAppManager


class WindowsAgent:
    """Agent running on Windows node responsible for local execution and telemetry."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.settings = settings or get_settings()
        self.registry = tool_registry or get_tool_registry()
        self.app_manager = WindowsAppManager()
        self._is_active = False

    def start(self) -> None:
        """Start the Windows Agent and register all tools."""
        register_default_tools(self.registry)
        self._is_active = True

    def stop(self) -> None:
        """Stop the Windows Agent."""
        self._is_active = False

    @property
    def is_active(self) -> bool:
        return self._is_active

    def get_health(self) -> Dict[str, Any]:
        """Produce a complete health status payload."""
        system_metrics = WindowsSystemCollector.collect(node_id=self.settings.node_id)
        gpu_info = WindowsSystemCollector.get_gpu_info()

        return {
            "status": "healthy" if self._is_active else "idle",
            "node_id": self.settings.node_id,
            "node_role": self.settings.node_role.value,
            "registered_tools_count": len(self.registry.list_tools()),
            "system": system_metrics.model_dump(),
            "gpu": gpu_info,
        }
