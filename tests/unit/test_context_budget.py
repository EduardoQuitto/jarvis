"""Tests for Context Budget (Phase 15.2)."""

import pytest

from core.context.budget import (
    ContextBudget,
    ProviderContextProfile,
    estimate_tokens,
    estimate_tools_tokens,
    get_provider_profile,
)
from core.contracts.llm import LLMToolDef, LLMFunctionSchema


class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        assert estimate_tokens("") == 0

    def test_basic_estimation(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_single_char_returns_one(self):
        assert estimate_tokens("x") == 1


class TestEstimateToolsTokens:
    def test_empty_list_returns_zero(self):
        assert estimate_tools_tokens([]) == 0

    def test_single_tool(self):
        tool = LLMToolDef(
            type="function",
            function=LLMFunctionSchema(
                name="echo",
                description="Echo a message",
                parameters={"type": "object", "properties": {}},
            ),
        )
        tokens = estimate_tools_tokens([tool])
        assert tokens > 0


class TestProviderContextProfile:
    def test_qwen35_4b_profile(self):
        profile = get_provider_profile("ollama", "qwen3.5:4b")
        assert profile.total_token_limit == 4096
        assert profile.effective_budget < 4096

    def test_qwen25_7b_profile(self):
        profile = get_provider_profile("ollama", "qwen2.5:7b")
        assert profile.total_token_limit == 32768

    def test_gemini_profile(self):
        profile = get_provider_profile("google", "gemini-3.7-flash")
        assert profile.total_token_limit == 1048576

    def test_unknown_model_fallback(self):
        profile = get_provider_profile("ollama", "unknown-model")
        assert profile.total_token_limit > 0

    def test_effective_budget_respects_safety_margin(self):
        profile = ProviderContextProfile("test", "test", 1000, 500, safety_margin=0.8)
        assert profile.effective_budget == 800


class TestContextBudget:
    def test_basic_allocation(self):
        budget = ContextBudget(total_tokens=4096, response_reserve=512)
        assert budget.available_tokens == 3584
        assert budget.allocate("system_prompt", 512)
        assert budget.sections["system_prompt"].used == 512

    def test_over_budget_allocation_fails(self):
        budget = ContextBudget(total_tokens=1024, response_reserve=256)
        assert budget.available_tokens == 768
        assert not budget.allocate("history", 1024)

    def test_register_usage(self):
        budget = ContextBudget(total_tokens=4096, response_reserve=512)
        budget.register_usage("system_prompt", 256)
        assert budget.sections["system_prompt"].used == 256
        assert budget.used_tokens == 256

    def test_remaining_tokens(self):
        budget = ContextBudget(total_tokens=4096, response_reserve=512)
        budget.register_usage("system_prompt", 1024)
        assert budget.remaining_tokens == 3584 - 1024

    def test_utilization(self):
        budget = ContextBudget(total_tokens=4096, response_reserve=0)
        budget.register_usage("test", 2048)
        assert budget.utilization == 0.5

    def test_is_over_budget(self):
        budget = ContextBudget(total_tokens=1024, response_reserve=256)
        budget.register_usage("test", 512)
        assert not budget.is_over_budget
        budget.register_usage("test2", 300)
        assert budget.is_over_budget

    def test_can_fit(self):
        budget = ContextBudget(total_tokens=1024, response_reserve=256)
        assert budget.can_fit(512)
        assert not budget.can_fit(1024)

    def test_from_profile(self):
        profile = ProviderContextProfile("ollama", "qwen3.5:4b", 4096, 4096)
        budget = ContextBudget.from_profile(profile)
        assert budget.total_tokens == profile.effective_budget
        assert budget.response_reserve == profile.response_reserve

    def test_summary(self):
        budget = ContextBudget(total_tokens=4096, response_reserve=512)
        budget.register_usage("system_prompt", 256)
        summary = budget.summary()
        assert summary["total_tokens"] == 4096
        assert summary["used_tokens"] == 256
        assert "system_prompt" in summary["sections"]
