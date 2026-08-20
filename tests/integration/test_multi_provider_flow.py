"""Integration tests for multi-provider orchestrator flow.

Tests the full pipeline: user message → IntelligenceRouter → LLM → tools → orchestrator → response.
"""

import pytest
from unittest.mock import patch

from core.llm.mock_provider import MockLLMProvider
from core.llm.registry import ProviderRegistry
from core.llm.router import IntelligenceRouter
from core.contracts.llm import LLMMessage, LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.orchestrator.engine import Orchestrator
from core.config import reset_settings


class TestOrchestratorWithRouter:
    """Test Orchestrator with IntelligenceRouter instead of direct provider."""

    def _make_orchestrator_with_mock_router(self, mock_provider=None):
        provider = mock_provider or MockLLMProvider()
        reg = ProviderRegistry()
        reg.register("mock", provider, priority=1.0)
        router = IntelligenceRouter(registry=reg)
        return Orchestrator(router=router), provider

    @pytest.mark.asyncio
    async def test_simple_conversation_via_router(self):
        orch, mock = self._make_orchestrator_with_mock_router()
        request = OrchestratorRequest(message="Hello JARVIS", device_id="test")
        response = await orch.process_message(request)
        assert response.session_id is not None
        assert response.response_text == mock._default_text
        assert response.error is None

    @pytest.mark.asyncio
    async def test_tool_call_via_router(self):
        mock = MockLLMProvider()
        mock.set_responses([
            LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id="call-r-001",
                        type="function",
                        function=LLMFunctionCall(
                            name="echo",
                            arguments={"message": "Router test"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="Done.",
                tool_calls=[],
                finish_reason="stop",
            ),
        ])

        orch, _ = self._make_orchestrator_with_mock_router(mock)
        request = OrchestratorRequest(message="Echo something", device_id="test")
        response = await orch.process_message(request)

        assert len(response.tool_calls_made) >= 1
        assert response.tool_calls_made[0].tool_name == "echo"
        assert response.tool_calls_made[0].success is True

    @pytest.mark.asyncio
    async def test_fallback_when_primary_fails(self):
        reg = ProviderRegistry()

        # Primary provider returns error
        bad = MockLLMProvider()
        bad.add_response(LLMResponse(
            content=None, tool_calls=[], finish_reason="stop",
            error_msg="Primary down",
        ))

        # Fallback provider works
        good = MockLLMProvider(default_text="Fallback response!")

        reg.register("bad", bad, priority=10.0)
        reg.register("good", good, priority=1.0)

        router = IntelligenceRouter(registry=reg)
        orch = Orchestrator(router=router)

        request = OrchestratorRequest(message="Hello", device_id="test")
        response = await orch.process_message(request)

        assert response.response_text == "Fallback response!"
        assert response.error is None

    @pytest.mark.asyncio
    async def test_direct_provider_still_works(self):
        """Backward compatibility: passing llm_provider directly still works."""
        mock = MockLLMProvider()
        orch = Orchestrator(llm_provider=mock)

        request = OrchestratorRequest(message="Hello", device_id="test")
        response = await orch.process_message(request)

        assert response.response_text == mock._default_text
        assert response.error is None


class TestChatAPIWithRouter:
    """Test the full HTTP → Router → Orchestrator → response flow."""

    @pytest.mark.asyncio
    async def test_chat_send_with_router(self):
        from httpx import AsyncClient, ASGITransport
        from server.app import create_app
        import server.routers.chat as chat_module

        # Patch the chat module's orchestrator
        mock_llm = MockLLMProvider()
        reg = ProviderRegistry()
        reg.register("mock", mock_llm, priority=1.0)
        router = IntelligenceRouter(registry=reg)
        chat_module._orchestrator = Orchestrator(router=router)

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/send",
                json={"message": "Hello JARVIS via router"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert len(data["response_text"]) > 0

    @pytest.mark.asyncio
    async def test_factory_create_router(self):
        with patch("core.config._settings", None):
            reset_settings()
            import os
            os.environ["JARVIS_LLM_PROVIDER"] = "mock"
            try:
                from core.llm.factory import create_router
                router = create_router()
                assert isinstance(router, IntelligenceRouter)
                status = router.get_status()
                assert status["total_count"] >= 2  # ollama + mock at minimum
            finally:
                os.environ.pop("JARVIS_LLM_PROVIDER", None)
                reset_settings()
