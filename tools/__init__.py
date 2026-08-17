"""Tools package entrypoint."""

from tools.base import FunctionalTool
from tools.registry import ToolRegistry, ToolNotFoundError, get_tool_registry
from tools.builtin import (
    EchoTool,
    GetSystemMetricsTool,
    ListProcessesTool,
    LaunchApplicationTool,
    CloseApplicationTool,
)


def register_default_tools(registry: ToolRegistry) -> None:
    """Populate registry with standard built-in tools."""
    registry.register(EchoTool())
    registry.register(GetSystemMetricsTool())
    registry.register(ListProcessesTool())
    registry.register(LaunchApplicationTool())
    registry.register(CloseApplicationTool())


__all__ = [
    "FunctionalTool",
    "ToolRegistry",
    "ToolNotFoundError",
    "get_tool_registry",
    "register_default_tools",
    "EchoTool",
    "GetSystemMetricsTool",
    "ListProcessesTool",
    "LaunchApplicationTool",
    "CloseApplicationTool",
]
