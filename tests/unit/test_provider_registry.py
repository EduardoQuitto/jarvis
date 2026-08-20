"""Tests for ProviderRegistry — provider registration, health caching, candidate selection."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.llm.registry import ProviderRegistry, ProviderEntry
from core.llm.mock_provider import MockLLMProvider


class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        mock = MockLLMProvider()
        reg.register("test", mock, priority=5.0, capabilities=["text_generation"])
        entry = reg.get("test")
        assert entry is not None
        assert entry.name == "test"
        assert entry.priority == 5.0
        assert reg.provider_count == 1

    def test_unregister(self):
        reg = ProviderRegistry()
        reg.register("test", MockLLMProvider())
        assert reg.unregister("test") is True
        assert reg.get("test") is None
        assert reg.provider_count == 0

    def test_unregister_nonexistent(self):
        reg = ProviderRegistry()
        assert reg.unregister("nope") is False

    def test_list_providers(self):
        reg = ProviderRegistry()
        reg.register("a", MockLLMProvider(), priority=1.0)
        reg.register("b", MockLLMProvider(), priority=2.0)
        providers = reg.list_providers()
        assert len(providers) == 2

    @pytest.mark.asyncio
    async def test_check_health_healthy(self):
        reg = ProviderRegistry(health_ttl=60)
        mock = MockLLMProvider(healthy=True)
        reg.register("test", mock)
        result = await reg.check_health("test")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self):
        reg = ProviderRegistry(health_ttl=60)
        mock = MockLLMProvider(healthy=False)
        reg.register("test", mock)
        result = await reg.check_health("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_caches_result(self):
        reg = ProviderRegistry(health_ttl=999)
        mock = MockLLMProvider(healthy=True)
        reg.register("test", mock)

        result1 = await reg.check_health("test")
        assert result1 is True

        # Second call should use cache (no health_check called)
        mock.health_check = AsyncMock(return_value=False)
        result2 = await reg.check_health("test")
        assert result2 is True  # Still cached as True

    @pytest.mark.asyncio
    async def test_invalidate_health(self):
        reg = ProviderRegistry(health_ttl=999)

        # Mock with configurable health_check
        mock = MockLLMProvider(healthy=True)
        health_tracker = AsyncMock(return_value=True)
        mock.health_check = health_tracker

        reg.register("test", mock)

        # First call caches the result
        result = await reg.check_health("test")
        assert result is True

        # Change return value — cached result won't see it yet
        health_tracker.return_value = False
        result_cached = await reg.check_health("test")
        assert result_cached is True

        # After invalidation, re-check calls provider.health_check() dynamically
        reg.invalidate_health("test")
        result = await reg.check_health("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_candidates_filters_unhealthy(self):
        reg = ProviderRegistry()
        healthy_mock = MockLLMProvider(healthy=True)
        unhealthy_mock = MockLLMProvider(healthy=False)
        reg.register("good", healthy_mock, priority=2.0)
        reg.register("bad", unhealthy_mock, priority=1.0)

        candidates = await reg.get_candidates()
        assert len(candidates) == 1
        assert candidates[0].name == "good"

    @pytest.mark.asyncio
    async def test_get_candidates_sorted_by_priority(self):
        reg = ProviderRegistry()
        reg.register("low", MockLLMProvider(), priority=1.0)
        reg.register("high", MockLLMProvider(), priority=10.0)
        reg.register("mid", MockLLMProvider(), priority=5.0)

        candidates = await reg.get_candidates()
        assert len(candidates) == 3
        assert candidates[0].name == "high"
        assert candidates[1].name == "mid"
        assert candidates[2].name == "low"

    @pytest.mark.asyncio
    async def test_get_candidates_filters_by_capability(self):
        reg = ProviderRegistry()
        reg.register("text-only", MockLLMProvider(), capabilities=["text_generation"])
        reg.register("vision", MockLLMProvider(), capabilities=["text_generation", "vision"])

        candidates = await reg.get_candidates(task_type="vision")
        assert len(candidates) == 1
        assert candidates[0].name == "vision"

    @pytest.mark.asyncio
    async def test_check_all_health(self):
        reg = ProviderRegistry()
        reg.register("a", MockLLMProvider(healthy=True))
        reg.register("b", MockLLMProvider(healthy=False))

        results = await reg.check_all_health()
        assert results["a"] is True
        assert results["b"] is False
