"""Integration tests for the end-to-end AI pipeline.

Tests the full flow: user message → conversation → LLM → tools → orchestrator → response.
Uses MockLLMProvider to simulate LLM behavior without Ollama.
"""

import pytest
from typing import List
from unittest.mock import AsyncMock, patch

from core.llm.mock_provider import MockLLMProvider
from core.llm.factory import create_llm_provider
from core.contracts.llm import LLMMessage, LLMResponse, LLMToolCall, LLMFunctionCall, LLMUsage
from core.contracts.orchestrator import OrchestratorRequest, OrchestratorResponse
from core.orchestrator.engine import Orchestrator
from core.config import reset_settings


# ============================================================
# Provider Factory Tests
# ============================================================

class TestProviderFactory:
    """Tests for the LLM provider factory."""

    def test_create_mock_provider(self):
        with patch("core.config._settings", None):
            reset_settings()
            provider = create_llm_provider("mock")
            assert isinstance(provider, MockLLMProvider)

    def test_create_ollama_provider(self):
        with patch("core.config._settings", None):
            reset_settings()
            provider = create_llm_provider("ollama")
            from core.llm.provider import OllamaProvider
            assert isinstance(provider, OllamaProvider)

    def test_create_unknown_provider_raises(self):
        with patch("core.config._settings", None):
            reset_settings()
            with pytest.raises(ValueError, match="Unsupported LLM provider"):
                create_llm_provider("nonexistent")

    def test_factory_uses_settings_by_default(self):
        with patch("core.config._settings", None):
            reset_settings()
            import os
            os.environ["JARVIS_LLM_PROVIDER"] = "mock"
            try:
                provider = create_llm_provider()
                assert isinstance(provider, MockLLMProvider)
            finally:
                os.environ.pop("JARVIS_LLM_PROVIDER", None)


# ============================================================
# Mock LLM Provider Tests
# ============================================================

class TestMockProviderE2E:
    """Tests for MockLLMProvider in end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        provider = MockLLMProvider()
        messages = [LLMMessage(role="user", content="Hello JARVIS")]
        response = await provider.generate(messages=messages)
        assert response.content is not None
        assert len(response.content) > 0
        assert response.error_msg is None

    @pytest.mark.asyncio
    async def test_auto_tool_call_response(self):
        provider = MockLLMProvider(auto_tool_calls=True)
        messages = [LLMMessage(role="user", content="Check system status")]
        response = await provider.generate(messages=messages)
        assert len(response.tool_calls) > 0
        assert response.tool_calls[0].function.name == "echo"

    @pytest.mark.asyncio
    async def test_error_response_has_error_msg(self):
        provider = MockLLMProvider()
        provider.add_response(LLMResponse(
            content=None,
            tool_calls=[],
            finish_reason="stop",
            error_msg="Ollama is not reachable",
        ))
        messages = [LLMMessage(role="user", content="Hello")]
        response = await provider.generate(messages=messages)
        assert response.error_msg == "Ollama is not reachable"

    @pytest.mark.asyncio
    async def test_queued_responses_cycle(self):
        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(content="First", tool_calls=[], finish_reason="stop"),
            LLMResponse(content="Second", tool_calls=[], finish_reason="stop"),
            LLMResponse(content="Third", tool_calls=[], finish_reason="stop"),
        ])
        messages = [LLMMessage(role="user", content="msg")]

        r1 = await provider.generate(messages=messages)
        r2 = await provider.generate(messages=messages)
        r3 = await provider.generate(messages=messages)
        r4 = await provider.generate(messages=messages)  # Falls back to default

        assert r1.content == "First"
        assert r2.content == "Second"
        assert r3.content == "Third"
        assert r4.content == provider._default_text


# ============================================================
# Orchestrator E2E Tests
# ============================================================

class TestOrchestratorE2E:
    """End-to-end tests for the Orchestrator agentic loop."""

    @pytest.mark.asyncio
    async def test_simple_conversation_flow(self):
        """User sends message, LLM responds with text, no tools needed."""
        llm = MockLLMProvider()
        orchestrator = Orchestrator(llm_provider=llm)

        request = OrchestratorRequest(
            message="Hello JARVIS, how are you?",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert response.session_id is not None
        assert len(response.session_id) > 0
        assert response.response_text == llm._default_text
        assert response.iterations_used >= 1
        assert len(response.tool_calls_made) == 0
        assert response.error is None

    @pytest.mark.asyncio
    async def test_tool_call_flow(self):
        """LLM calls echo tool, sees result, then responds with text."""
        # First call: LLM requests echo tool
        # Second call: LLM sees tool result and responds
        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-test-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="echo",
                            arguments={"message": "System check complete"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ),
            LLMResponse(
                content="System check complete. All systems operational.",
                tool_calls=[],
                finish_reason="stop",
                model="mock-model",
            ),
        ])

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Run a system check",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert response.session_id is not None
        assert "System check complete" in response.response_text or "operational" in response.response_text
        assert len(response.tool_calls_made) >= 1
        assert response.tool_calls_made[0].tool_name == "echo"
        assert response.tool_calls_made[0].success is True

    @pytest.mark.asyncio
    async def test_nonexistent_tool_handled(self):
        """LLM calls a tool that doesn't exist — should return error in tool result."""
        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-bad-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="nonexistent_tool",
                            arguments={"foo": "bar"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ),
            LLMResponse(
                content="The tool doesn't exist.",
                tool_calls=[],
                finish_reason="stop",
                model="mock-model",
            ),
        ])

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Use nonexistent_tool",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert response.session_id is not None
        assert len(response.tool_calls_made) >= 1
        assert response.tool_calls_made[0].success is False
        assert "not registered" in response.tool_calls_made[0].error

    @pytest.mark.asyncio
    async def test_llm_error_handled(self):
        """LLM returns error_msg — orchestrator returns error response."""
        provider = MockLLMProvider()
        provider.add_response(LLMResponse(
            content=None,
            tool_calls=[],
            finish_reason="stop",
            error_msg="Ollama is not reachable",
        ))

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Hello",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert response.error == "Ollama is not reachable"
        assert "Ollama is not reachable" in response.response_text

    @pytest.mark.asyncio
    async def test_confirmation_flow(self):
        """LLM calls a YELLOW tool without confirmation — orchestrator pauses."""
        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-yellow-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="launch_application",
                            arguments={"app_name": "notepad"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ),
        ])

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Open notepad",
            device_id="test-device",
            confirmed=False,
        )
        response = await orchestrator.process_message(request)

        assert response.needs_confirmation is True
        assert response.confirmation_id is not None
        assert "launch_application" in response.confirmation_details

    @pytest.mark.asyncio
    async def test_confirmation_approved_flow(self):
        """User confirms a YELLOW tool, orchestrator re-processes."""
        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-y-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="launch_application",
                            arguments={"app_name": "notepad"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ),
            LLMResponse(
                content="Notepad is now open.",
                tool_calls=[],
                finish_reason="stop",
                model="mock-model",
            ),
        ])

        orchestrator = Orchestrator(llm_provider=provider)

        # Step 1: Initial message
        request = OrchestratorRequest(
            message="Open notepad",
            device_id="test-device",
            confirmed=False,
        )
        response = await orchestrator.process_message(request)
        assert response.needs_confirmation is True
        cid = response.confirmation_id
        session_id = response.session_id

        # Step 2: User confirms
        confirm_request = OrchestratorRequest(
            message="Yes, open it",
            session_id=session_id,
            device_id="test-device",
            confirmed=True,
            confirmation_id=cid,
        )
        confirm_response = await orchestrator.process_message(confirm_request)
        assert confirm_response.session_id == session_id

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self):
        """LLM keeps calling tools indefinitely — hits iteration limit."""
        provider = MockLLMProvider()

        # Create 11 identical tool call responses (max is 10)
        tool_call_responses = []
        for i in range(11):
            tool_call_responses.append(LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id=f"call-{i:03d}",
                        type="function",
                        function=LLMFunctionCall(
                            name="echo",
                            arguments={"message": f"Iteration {i}"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ))
        provider.set_responses(tool_call_responses)

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Keep calling echo forever",
            device_id="test-device",
        )
        response = await orchestrator.process_message(request)

        assert "maximum number of tool call iterations" in response.response_text
        assert response.iterations_used >= 10

    @pytest.mark.asyncio
    async def test_session_persistence(self):
        """Messages are persisted to conversation history across calls."""
        llm = MockLLMProvider()
        orchestrator = Orchestrator(llm_provider=llm)

        # First message
        request1 = OrchestratorRequest(
            message="My name is Sergio",
            device_id="test-device",
        )
        response1 = await orchestrator.process_message(request1)
        session_id = response1.session_id

        # Second message in same session
        request2 = OrchestratorRequest(
            message="What's my name?",
            session_id=session_id,
            device_id="test-device",
        )
        response2 = await orchestrator.process_message(request2)

        assert response2.session_id == session_id

        # Verify conversation history exists
        history = await orchestrator._conversation.get_history(session_id)
        assert len(history) >= 2
        assert history[0].content == "My name is Sergio"

    @pytest.mark.asyncio
    async def test_create_task_tool(self):
        """LLM calls create_task to create a background task."""
        from core.task.manager import TaskManager

        provider = MockLLMProvider()
        provider.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-task-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="create_task",
                            arguments={
                                "objective": "Organize the Downloads folder",
                                "priority": "normal",
                            },
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            ),
            LLMResponse(
                content="Task created. I'll organize your Downloads folder.",
                tool_calls=[],
                finish_reason="stop",
                model="mock-model",
            ),
        ])

        orchestrator = Orchestrator(llm_provider=provider)
        request = OrchestratorRequest(
            message="Organize my Downloads folder",
            device_id="test-device",
            confirmed=True,
        )
        response = await orchestrator.process_message(request)

        assert len(response.tool_calls_made) >= 1
        tc = response.tool_calls_made[0]
        assert tc.tool_name == "create_task"
        assert tc.success is True
        assert tc.data["task_id"].startswith("task-")
        assert tc.data["objective"] == "Organize the Downloads folder"


# ============================================================
# Chat API Integration Tests
# ============================================================

class TestChatAPIIntegration:
    """Test the full HTTP → Orchestrator → response flow."""

    @pytest.mark.asyncio
    async def test_chat_send_with_mock_provider(self):
        from httpx import AsyncClient, ASGITransport
        from server.app import create_app

        # Patch the chat router's LLM provider to use mock
        import server.routers.chat as chat_module
        from core.llm.mock_provider import MockLLMProvider

        mock_llm = MockLLMProvider()
        chat_module._orchestrator = Orchestrator(llm_provider=mock_llm)

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/send",
                json={"message": "Hello JARVIS"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert "response_text" in data
            assert len(data["response_text"]) > 0

    @pytest.mark.asyncio
    async def test_chat_confirm_endpoint(self):
        from httpx import AsyncClient, ASGITransport
        from server.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/confirm",
                json={"confirmation_id": "test-cid-123", "approved": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_chat_pending_endpoint(self):
        from httpx import AsyncClient, ASGITransport
        from server.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/chat/confirm/pending")
            assert response.status_code == 200
            assert isinstance(response.json(), list)
