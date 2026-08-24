"""Tests for provider visibility filtering: external gets only SHARED, local gets all."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from core.contracts.enums import ToolVisibility
from core.conversation.context_builder import ContextBuilder


class TestProviderVisibility:
    """ContextBuilder.build_tools_list filters by provider locality."""

    def test_local_provider_sees_all_tools(self):
        builder = ContextBuilder()
        tool_meta = MagicMock()
        tool_meta.visibility = ToolVisibility.LOCAL_ONLY
        tool_meta.name = "launch_application"
        tool_meta.description = "Launch"
        tool_meta.security_level = MagicMock()
        tool_meta.security_level.value = "YELLOW"
        tool_meta.parameters_schema = {"type": "object", "properties": {}}

        tools = builder.build_tools_list([tool_meta], shared_only=False)
        assert len(tools) == 1

    def test_external_provider_sees_only_shared(self):
        builder = ContextBuilder()
        local_meta = MagicMock()
        local_meta.visibility = ToolVisibility.LOCAL_ONLY
        local_meta.name = "launch_application"

        shared_meta = MagicMock()
        shared_meta.visibility = ToolVisibility.SHARED
        shared_meta.name = "echo"
        shared_meta.description = "Echo"
        shared_meta.security_level = MagicMock()
        shared_meta.security_level.value = "GREEN"
        shared_meta.parameters_schema = {"type": "object", "properties": {}}

        tools = builder.build_tools_list([local_meta, shared_meta], shared_only=True)
        assert len(tools) == 1
        assert tools[0].function.name == "echo"

    def test_shared_only_empty_when_no_shared_tools(self):
        builder = ContextBuilder()
        local_meta = MagicMock()
        local_meta.visibility = ToolVisibility.LOCAL_ONLY
        local_meta.name = "read_file"

        tools = builder.build_tools_list([local_meta], shared_only=True)
        assert len(tools) == 0
