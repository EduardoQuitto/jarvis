"""Unit tests for the LLM layer, conversation manager, orchestrator, and new components."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import json


# ============================================================
# LLM Tests
# ============================================================

class TestMockLLMProvider:
    """Tests for the MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_generate_text_response(self):
        from core.llm.mock_provider import MockLLMProvider
        from core.contracts.llm import LLMMessage

        provider = MockLLMProvider()
        messages = [LLMMessage(role="user", content="Hello")]
        response = await provider.generate(messages=messages)

        assert response.content is not None
        assert len(response.content) > 0
        assert response.tool_calls is None or len(response.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_generate_with_tool_calls(self):
        from core.llm.mock_provider import MockLLMProvider
        from core.contracts.llm import LLMMessage

        provider = MockLLMProvider(auto_tool_calls=True)
        messages = [LLMMessage(role="user", content="Run a tool")]
        response = await provider.generate(messages=messages)

        assert response.tool_calls is not None
        assert len(response.tool_calls) > 0

    @pytest.mark.asyncio
    async def test_health_check(self):
        from core.llm.mock_provider import MockLLMProvider

        provider = MockLLMProvider()
        healthy = await provider.health_check()
        assert healthy is True


class TestLLMConverters:
    """Tests for LLM tool converters."""

    def test_tools_metadata_to_llm_defs(self):
        from core.llm.converters import tools_metadata_to_llm_defs
        from core.contracts.tool import ToolMetadata
        from core.contracts.enums import SecurityLevel

        metadata = [
            ToolMetadata(
                name="test_tool",
                description="A test tool",
                security_level=SecurityLevel.GREEN,
                parameters={"msg": {"type": "string", "description": "Message"}},
            )
        ]
        defs = tools_metadata_to_llm_defs(metadata)
        assert len(defs) == 1
        assert defs[0].function.name == "test_tool"

    def test_create_tool_call_id(self):
        from core.llm.converters import create_tool_call_id
        tc_id = create_tool_call_id()
        assert tc_id.startswith("call-")
        assert len(tc_id) > 5


# ============================================================
# Conversation Manager Tests
# ============================================================

class TestConversationManager:
    """Tests for the ConversationManager."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        from core.conversation.manager import ConversationManager

        manager = ConversationManager()
        session_id = await manager.create_session(
            title="Test Conversation",
            device_id="test-device",
        )
        assert session_id is not None
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_append_and_get_messages(self):
        from core.conversation.manager import ConversationManager

        manager = ConversationManager()
        session_id = await manager.create_session(title="Test")

        await manager.append_message(session_id, "user", "Hello")
        await manager.append_message(session_id, "assistant", "Hi there!")

        messages = await manager.get_history(session_id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_get_context_window(self):
        from core.conversation.manager import ConversationManager

        manager = ConversationManager()
        session_id = await manager.create_session(title="Test")

        for i in range(5):
            await manager.append_message(session_id, "user", f"Message {i}")

        history = await manager.get_context_window(session_id)
        assert len(history) == 5


# ============================================================
# Event Bus Tests
# ============================================================

class TestEventBus:
    """Tests for the EventBus."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        from core.events.bus import EventBus
        from core.events.models import EventType, SystemEvent

        bus = EventBus()
        received = []

        async def callback(event):
            received.append(event)

        bus.subscribe(EventType.USER_MESSAGE, callback)
        event = SystemEvent(
            event_type=EventType.USER_MESSAGE,
            source="test",
            data={"message": "hello"},
        )
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].event_type == EventType.USER_MESSAGE

    def test_history(self):
        from core.events.bus import EventBus
        from core.events.models import EventType, SystemEvent

        bus = EventBus()
        bus._history.append(SystemEvent(
            event_type=EventType.SYSTEM_STATUS,
            source="test",
            data={},
        ))
        history = bus.get_history(limit=10)
        assert len(history) == 1


# ============================================================
# Orchestrator Tests
# ============================================================

class TestOrchestrator:
    """Tests for the Orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_process_message(self):
        from core.orchestrator.engine import Orchestrator
        from core.llm.mock_provider import MockLLMProvider
        from core.contracts.orchestrator import OrchestratorRequest

        llm = MockLLMProvider()
        orchestrator = Orchestrator(llm_provider=llm)

        request = OrchestratorRequest(
            message="Hello JARVIS",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert response.session_id is not None
        assert len(response.response_text) > 0
        assert response.iterations_used >= 1


# ============================================================
# Task Manager Tests
# ============================================================

class TestTaskManager:
    """Tests for the TaskManager."""

    @pytest.mark.asyncio
    async def test_create_and_get_task(self):
        from core.task.manager import TaskManager

        manager = TaskManager()
        task = await manager.create_task(
            objective="Test objective",
            context={"test": True},
        )
        assert task.task_id is not None
        assert task.objective == "Test objective"

        retrieved = await manager.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id


# ============================================================
# Confirmation Manager Tests
# ============================================================

class TestConfirmationManager:
    """Tests for the ConfirmationManager."""

    @pytest.mark.asyncio
    async def test_request_and_approve(self):
        from core.orchestrator.confirmation import ConfirmationManager

        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="test_tool",
            arguments={"arg": "value"},
            security_level="YELLOW",
            reason="Test confirmation",
        )
        assert cid is not None

        # Approve
        approved = manager.approve(cid)
        assert approved is True

        # Wait should return True immediately
        result = await manager.wait_for_confirmation(cid, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_deny(self):
        from core.orchestrator.confirmation import ConfirmationManager

        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="test_tool",
            arguments={},
            security_level="RED",
            reason="Dangerous action",
        )

        denied = manager.deny(cid)
        assert denied is True

        result = await manager.wait_for_confirmation(cid, timeout=1.0)
        assert result is False

    def test_list_pending(self):
        import asyncio
        from core.orchestrator.confirmation import ConfirmationManager

        manager = ConfirmationManager()
        loop = asyncio.new_event_loop()
        cid = loop.run_until_complete(
            manager.request_confirmation(
                tool_name="test",
                arguments={},
                security_level="YELLOW",
                reason="test",
            )
        )
        pending = manager.list_pending()
        assert len(pending) >= 1
        loop.close()


# ============================================================
# Device Registry Tests
# ============================================================

class TestDeviceRegistry:
    """Tests for the DeviceRegistry."""

    @pytest.mark.asyncio
    async def test_register_and_get_device(self):
        from core.device.registry import DeviceRegistry
        from core.contracts.device import (
            DeviceRegistrationRequest,
            DeviceType,
            DeviceCapability,
        )

        registry = DeviceRegistry()
        request = DeviceRegistrationRequest(
            device_id="test-device-001",
            name="Test Device",
            device_type=DeviceType.CORE,
            capabilities=[DeviceCapability.LLM, DeviceCapability.VISION],
            version="0.1.0",
        )
        device = await registry.register_device(request)
        assert device is not None
        assert device.device_id == "test-device-001"

        retrieved = await registry.get_device("test-device-001")
        assert retrieved is not None


# ============================================================
# MCP Server Tests
# ============================================================

class TestMCPServer:
    """Tests for the MCP Server."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        from core.mcp.server import MCPServer

        server = MCPServer()
        result = await server.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {},
            "id": 1,
        })
        assert result["result"]["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_tools_list(self):
        from core.mcp.server import MCPServer

        server = MCPServer()
        result = await server.handle_request({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2,
        })
        assert "tools" in result["result"]

    @pytest.mark.asyncio
    async def test_ping(self):
        from core.mcp.server import MCPServer

        server = MCPServer()
        result = await server.handle_request({
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {},
            "id": 3,
        })
        assert result["result"] == {}


# ============================================================
# System Prompt Tests
# ============================================================

class TestSystemPrompt:
    """Tests for the system prompt builder."""

    def test_build_system_prompt(self):
        from core.orchestrator.system_prompt import build_system_prompt

        prompt = build_system_prompt(
            device_id="test-device",
            device_capabilities=["llm", "vision"],
            available_tool_names=["echo", "read_file"],
        )

        assert "J.A.R.V.I.S." in prompt
        assert "test-device" in prompt
        assert "echo" in prompt
        assert "read_file" in prompt

    def test_build_prompt_no_tools(self):
        from core.orchestrator.system_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "J.A.R.V.I.S." in prompt
        assert "Available Tools" not in prompt
