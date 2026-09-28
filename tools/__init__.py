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
from tools.builtin.task_tool import CreateTaskTool
from tools.builtin.remote_tool import RemoteServerTool, register_remote_tool
from tools.builtin.network_tool import PingHostTool, DnsLookupTool, GetNetworkInterfacesTool
from tools.builtin.notification_tool import SendNotificationTool, CheckPendingNotificationsTool
from tools.builtin.filesystem_analysis_tool import FindDuplicatesTool, DiskUsageAnalysisTool
from tools.builtin.security_tool import GeneratePasswordTool, HashFileTool, VerifyChecksumTool
from tools.builtin.utility_tool import CalculateMathTool
from tools.builtin.system_info_tool import GetSystemInfoTool, GetSystemUptimeTool
from tools.builtin.home_assistant import (
    HomeAssistantGetStateTool,
    HomeAssistantGetStatesTool,
    HomeAssistantCallServiceTool,
    HomeAssistantWakeOnLanTool,
    register_home_assistant_tools,
)


def register_default_tools(registry: ToolRegistry) -> None:
    """Populate registry with standard built-in tools.

    The CORE -> SERVER bridge tool (remote_server_tool) is registered only
    when JARVIS_SERVER_URL is configured; otherwise the system works exactly
    as before without errors.

    Home Assistant tools execute only on SERVER nodes with HA enabled; the
    CORE reaches them through remote_server_tool (never directly).
    """
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
    registry.register(CreateTaskTool())
    registry.register(PingHostTool())
    registry.register(DnsLookupTool())
    registry.register(GetNetworkInterfacesTool())
    registry.register(SendNotificationTool())
    registry.register(CheckPendingNotificationsTool())
    registry.register(FindDuplicatesTool())
    registry.register(DiskUsageAnalysisTool())
    registry.register(GeneratePasswordTool())
    registry.register(HashFileTool())
    registry.register(VerifyChecksumTool())
    registry.register(CalculateMathTool())
    registry.register(GetSystemInfoTool())
    registry.register(GetSystemUptimeTool())
    register_remote_tool(registry)
    register_home_assistant_tools(registry)


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
    "CreateTaskTool",
    "PingHostTool",
    "DnsLookupTool",
    "GetNetworkInterfacesTool",
    "SendNotificationTool",
    "CheckPendingNotificationsTool",
    "FindDuplicatesTool",
    "DiskUsageAnalysisTool",
    "GeneratePasswordTool",
    "HashFileTool",
    "VerifyChecksumTool",
    "CalculateMathTool",
    "GetSystemInfoTool",
    "GetSystemUptimeTool",
    "RemoteServerTool",
    "register_remote_tool",
    "HomeAssistantGetStateTool",
    "HomeAssistantGetStatesTool",
    "HomeAssistantCallServiceTool",
    "HomeAssistantWakeOnLanTool",
    "register_home_assistant_tools",
]
