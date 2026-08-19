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
from tools.builtin.file_tool import ReadFileTool, WriteFileTool, ListDirTool
from tools.builtin.time_tool import GetCurrentTimeTool
from tools.builtin.screenshot_tool import ScreenshotTool
from tools.builtin.memory_tool import SearchMemoryTool
from tools.builtin.internet_tool import WebSearchTool, FetchUrlTool


def register_default_tools(registry: ToolRegistry) -> None:
    """Populate registry with standard built-in tools."""
    registry.register(EchoTool())
    registry.register(GetSystemMetricsTool())
    registry.register(ListProcessesTool())
    registry.register(LaunchApplicationTool())
    registry.register(CloseApplicationTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListDirTool())
    registry.register(GetCurrentTimeTool())
    registry.register(ScreenshotTool())
    registry.register(SearchMemoryTool())
    registry.register(WebSearchTool())
    registry.register(FetchUrlTool())


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
    "ReadFileTool",
    "WriteFileTool",
    "ListDirTool",
    "GetCurrentTimeTool",
    "ScreenshotTool",
    "SearchMemoryTool",
    "WebSearchTool",
    "FetchUrlTool",
]
