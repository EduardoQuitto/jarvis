"""Tests for Tool Context Selection (Phase 15.2)."""

import pytest

from core.context.tool_selector import ToolContextSelector, ToolSelectionResult
from core.contracts.tool import ToolMetadata
from core.contracts.enums import SecurityLevel, ToolVisibility


def _make_tool(name: str, description: str, visibility: ToolVisibility = ToolVisibility.LOCAL_ONLY) -> ToolMetadata:
    return ToolMetadata(
        name=name,
        description=description,
        security_level=SecurityLevel.GREEN,
        visibility=visibility,
        parameters_schema={"type": "object", "properties": {}},
    )


class TestToolContextSelector:
    def test_empty_tools_returns_empty(self):
        selector = ToolContextSelector()
        result = selector.select([], query="hello")
        assert result.selected_tools == []
        assert result.confidence == 0.0

    def test_selects_relevant_tools(self):
        selector = ToolContextSelector()
        tools = [
            _make_tool("read_file", "Read a file from disk"),
            _make_tool("get_cpu", "Get CPU usage"),
            _make_tool("echo", "Echo a message"),
        ]
        result = selector.select(tools, query="read the file")
        names = [t.name for t in result.selected_tools]
        assert "read_file" in names

    def test_always_includes_core_tools(self):
        selector = ToolContextSelector()
        tools = [
            _make_tool("read_file", "Read a file"),
            _make_tool("get_cpu", "Get CPU usage"),
            _make_tool("echo", "Echo a message"),
            _make_tool("get_time", "Get current time"),
        ]
        result = selector.select(tools, query="something random")
        names = {t.name for t in result.selected_tools}
        assert "echo" in names
        assert "get_time" in names

    def test_fallback_on_low_confidence(self):
        selector = ToolContextSelector(confidence_threshold=0.5, max_tools=3)
        tools = [
            _make_tool("read_file", "Read a file from disk"),
            _make_tool("get_cpu", "Get CPU usage"),
            _make_tool("get_memory", "Get memory usage"),
            _make_tool("get_disk", "Get disk usage"),
            _make_tool("get_network", "Get network status"),
        ]
        result = selector.select(tools, query="xyz")
        assert result.fallback_used
        assert len(result.selected_tools) > 3

    def test_no_fallback_on_high_confidence(self):
        selector = ToolContextSelector(confidence_threshold=0.1)
        tools = [
            _make_tool("read_file", "Read a file from disk"),
            _make_tool("get_cpu", "Get CPU usage"),
        ]
        result = selector.select(tools, query="read file")
        assert not result.fallback_used

    def test_respects_shared_only(self):
        selector = ToolContextSelector()
        tools = [
            _make_tool("read_file", "Read a file", ToolVisibility.LOCAL_ONLY),
            _make_tool("web_search", "Search the web", ToolVisibility.SHARED),
            _make_tool("get_cpu", "Get CPU", ToolVisibility.LOCAL_ONLY),
        ]
        result = selector.select(tools, query="search", shared_only=True)
        names = {t.name for t in result.selected_tools}
        assert "web_search" in names
        assert "read_file" not in names

    def test_max_tools_respected(self):
        selector = ToolContextSelector(max_tools=3)
        tools = [_make_tool(f"tool_{i}", f"Tool number {i}") for i in range(10)]
        result = selector.select(tools, query="tool")
        assert len(result.selected_tools) <= 3

    def test_min_tools_respected(self):
        selector = ToolContextSelector(min_tools=3, max_tools=5)
        tools = [
            _make_tool("read_file", "Read a file"),
            _make_tool("get_cpu", "Get CPU usage"),
        ]
        result = selector.select(tools, query="read")
        assert len(result.selected_tools) >= 2

    def test_selection_result_metadata(self):
        selector = ToolContextSelector()
        tools = [_make_tool("read_file", "Read a file")]
        result = selector.select(tools, query="read file")
        assert isinstance(result, ToolSelectionResult)
        assert result.confidence > 0
        assert result.selection_reason != ""
