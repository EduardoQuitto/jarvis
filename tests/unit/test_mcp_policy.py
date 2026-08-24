"""Tests for MCP policy enforcement: YELLOW blocked, GREEN allowed."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.contracts.enums import SecurityLevel
from core.contracts.tool import ToolMetadata
from security.policy_engine import PolicyEngine


class TestMCPPolicy:
    """MCP server should block YELLOW/RED tools, allow GREEN."""

    def test_green_tool_accepted(self):
        engine = PolicyEngine()
        tool = ToolMetadata(
            name="echo", description="Echo",
            security_level=SecurityLevel.GREEN,
            parameters_schema={"type": "object", "properties": {}},
        )
        decision = engine.evaluate(tool, {}, confirmed=False)
        assert decision.allowed is True
        assert decision.requires_confirmation is False

    def test_yellow_tool_requires_confirmation(self):
        engine = PolicyEngine()
        tool = ToolMetadata(
            name="read_file", description="Read",
            security_level=SecurityLevel.YELLOW,
            parameters_schema={"type": "object", "properties": {"file_path": {"type": "string"}}},
        )
        decision = engine.evaluate(tool, {"file_path": "/tmp/test.txt"}, confirmed=False)
        assert decision.allowed is False
        assert decision.requires_confirmation is True

    def test_yellow_tool_blocked_in_mcp(self):
        """Simulates MCP server response: YELLOW tool → returns error to client."""
        engine = PolicyEngine()
        tool = ToolMetadata(
            name="launch_application", description="Launch",
            security_level=SecurityLevel.YELLOW,
            parameters_schema={"type": "object", "properties": {"app_name": {"type": "string"}}},
        )
        decision = engine.evaluate(tool, {"app_name": "notepad"}, confirmed=False)
        # MCP server checks this: if requires_confirmation → send error
        assert decision.requires_confirmation is True

    def test_yellow_tool_allowed_if_confirmed(self):
        engine = PolicyEngine()
        tool = ToolMetadata(
            name="read_file", description="Read",
            security_level=SecurityLevel.YELLOW,
            parameters_schema={"type": "object", "properties": {"file_path": {"type": "string"}}},
        )
        decision = engine.evaluate(tool, {"file_path": "/tmp/test.txt"}, confirmed=True)
        assert decision.allowed is True
