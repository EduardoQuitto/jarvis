"""Tests for IntelligenceRouter — provider selection, fallback, circuit breaker."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm.router import IntelligenceRouter, CircuitBreaker
from core.llm.registry import ProviderRegistry
from core.llm.mock_provider import MockLLMProvider
from core.contracts.llm import LLMMessage, LLMResponse


class TestCircuitBreaker:
    def test_closed_by_default(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        assert cb.is_open("test") is False

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)
        cb.record_failure("p")
        assert cb.is_open("p") is False
        cb.record_failure("p")
        assert cb.is_open("p") is True

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)
        cb.record_failure("p")
        cb.record_failure("p")
        assert cb.is_open("p") is True
        cb.record_success("p")
        assert cb.is_open("p") is False

    def test_manual_reset(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=999)
        cb.record_failure("p")
        assert cb.is_open("p") is True
        cb.reset("p")
        assert cb.is_open("p") is False

    def test_different_providers_independent(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=999)
        cb.record_failure("a")
        assert cb.is_open("a") is True
        assert cb.is_open("b") is False


class TestIntelligenceRouter:
    def _make_router(self, providers=None):
        reg = ProviderRegistry()
        if providers:
            for name, mock, priority in providers:
                reg.register(name, mock, priority=priority)
        else:
            reg.register("mock", MockLLMProvider(), priority=1.0)
        return IntelligenceRouter(registry=reg)

    @pytest.mark.asyncio
    async def test_route_simple_response(self):
        router = self._make_router()
        msgs = [LLMMessage(role="user", content="Hello")]
        response = await router.route(messages=msgs)
        assert response.error_msg is None
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_route_returns_error_when_no_providers(self):
        reg = ProviderRegistry()
        router = IntelligenceRouter(registry=reg)
        response = await router.route(messages=[LLMMessage(role="user", content="Hi")])
        assert response.error_msg is not None
        assert "No healthy" in response.error_msg

    @pytest.mark.asyncio
    async def test_route_fallback_on_failure(self):
        reg = ProviderRegistry()

        bad = MockLLMProvider()
        bad.add_response(LLMResponse(
            content=None, tool_calls=[], finish_reason="stop",
            error_msg="Provider down",
        ))

        good = MockLLMProvider(default_text="Fallback worked!")

        reg.register("bad", bad, priority=10.0)
        reg.register("good", good, priority=1.0)

        router = IntelligenceRouter(registry=reg)
        response = await router.route(messages=[LLMMessage(role="user", content="Hi")])
        assert response.content == "Fallback worked!"
        assert response.error_msg is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_repeated_failures(self):
        reg = ProviderRegistry()
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)

        bad = MockLLMProvider()
        # Need enough error responses so both calls fail
        bad.set_responses([
            LLMResponse(content=None, tool_calls=[], finish_reason="stop", error_msg="Error"),
            LLMResponse(content=None, tool_calls=[], finish_reason="stop", error_msg="Error"),
        ])

        reg.register("bad", bad, priority=10.0)

        router = IntelligenceRouter(registry=reg, circuit_breaker=cb)

        # Two failures should open the circuit
        await router.route(messages=[LLMMessage(role="user", content="1")])
        await router.route(messages=[LLMMessage(role="user", content="2")])
        assert cb.is_open("bad") is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self):
        reg = ProviderRegistry()
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)

        flaky = MockLLMProvider()
        flaky.add_response(LLMResponse(
            content=None, tool_calls=[], finish_reason="stop",
            error_msg="Error",
        ))
        flaky.add_response(LLMResponse(
            content="OK", tool_calls=[], finish_reason="stop",
        ))

        reg.register("flaky", flaky, priority=10.0)
        router = IntelligenceRouter(registry=reg, circuit_breaker=cb)

        # First call fails
        r1 = await router.route(messages=[LLMMessage(role="user", content="1")])
        assert r1.error_msg is not None

        # Second call succeeds → resets circuit
        r2 = await router.route(messages=[LLMMessage(role="user", content="2")])
        assert r2.content == "OK"
        assert cb.is_open("flaky") is False

    @pytest.mark.asyncio
    async def test_route_skips_unhealthy_providers(self):
        reg = ProviderRegistry()
        reg.register("unhealthy", MockLLMProvider(healthy=False), priority=10.0)
        reg.register("healthy", MockLLMProvider(healthy=True), priority=1.0)

        router = IntelligenceRouter(registry=reg)
        response = await router.route(messages=[LLMMessage(role="user", content="Hi")])
        assert response.error_msg is None
        assert response.content is not None

    def test_get_status(self):
        router = self._make_router()
        status = router.get_status()
        assert "providers" in status
        assert status["total_count"] == 1
        assert status["healthy_count"] == 1
