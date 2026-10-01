"""Regression tests for per-call context rebuild (Phase 15.2 fix).

Proves that EVERY LLM call — first turn, post-tool-call iterations, and
streaming — goes through the budget enforcement, and that max_tokens is
derived from the provider profile (never hardcoded in the Orchestrator).
"""

import pytest

from core.config import reset_settings
from core.context.budget import (
    ContextBudget,
    ProviderContextProfile,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    estimate_tools_tokens,
    get_provider_profile,
)
from core.context.tool_selector import ToolContextSelector
from core.contracts.llm import (
    LLMFunctionCall,
    LLMFunctionSchema,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDef,
)
from core.contracts.orchestrator import OrchestratorRequest
from core.conversation.context_builder import ContextBuilder
from core.orchestrator.engine import Orchestrator
from tests.unit.tool_sequence_check import assert_valid_tool_sequence


def _tc(call_id="call-1", name="echo", arguments=None):
    return LLMToolCall(
        id=call_id, type="function",
        function=LLMFunctionCall(name=name, arguments=arguments or {"message": "hi"}),
    )


def _tool_call_response(name="echo", arguments=None, call_id="call-1"):
    return LLMResponse(
        content=None,
        tool_calls=[_tc(call_id, name, arguments)],
        finish_reason="tool_calls",
    )


def _text_response(text="done!"):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop")


class SpyProvider:
    """Minimal recording provider: scripted responses, full call capture."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def _next(self):
        if self._responses:
            return self._responses.pop(0)
        return _text_response("default")

    async def generate(self, messages, tools=None, temperature=0.7, max_tokens=None):
        self.calls.append({
            "method": "generate",
            "messages": list(messages),
            "tools": list(tools) if tools else [],
            "max_tokens": max_tokens,
        })
        return await self._next()

    async def generate_stream(self, messages, tools=None, temperature=0.7, max_tokens=None):
        from core.contracts.llm import StreamChunk
        self.calls.append({
            "method": "generate_stream",
            "messages": list(messages),
            "tools": list(tools) if tools else [],
            "max_tokens": max_tokens,
        })
        resp = await self._next()
        if resp.tool_calls:
            yield StreamChunk(content_delta="", tool_calls_deltas=resp.tool_calls,
                              finish_reason="tool_calls")
        else:
            yield StreamChunk(content_delta=resp.content or "", finish_reason="stop")

    async def health_check(self) -> bool:
        return True

    def get_model_info(self):
        return {"provider": "spy", "model": "spy-model"}


def _prompt_tokens(call):
    return estimate_messages_tokens(call["messages"]) + estimate_tools_tokens(call["tools"])


@pytest.fixture
def qwen_profile(monkeypatch):
    monkeypatch.setenv("JARVIS_CONTEXT_BUDGET_ENABLED", "true")
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "qwen3.5:4b")
    reset_settings()
    return get_provider_profile("ollama", "qwen3.5:4b")


class TestBudgetAccountsTools:
    def test_tool_definitions_enter_budget(self, qwen_profile):
        from core.context.manager import ContextWindowManager
        budget = ContextBudget.from_profile(qwen_profile)
        wm = ContextWindowManager(budget=budget)
        tools = [
            LLMToolDef(
                type="function",
                function=LLMFunctionSchema(
                    name=f"tool_{i}", description="does things " + "x" * 50,
                    parameters={"type": "object", "properties": {}},
                ),
            )
            for i in range(28)
        ]
        assert estimate_tools_tokens(tools) > 0
        result = wm.build_context(
            [LLMMessage(role="user", content="hi")],
            system_prompt="sys",
            tools=tools,
        )
        summary = budget.summary()
        assert "tool_definitions" in summary["sections"]
        assert summary["sections"]["tool_definitions"]["used"] == estimate_tools_tokens(tools)

    def test_tool_calls_enter_history_estimate(self):
        plain = LLMMessage(role="assistant", content="")
        with_calls = LLMMessage(role="assistant", content="", tool_calls=[_tc()])
        assert estimate_message_tokens(with_calls) > estimate_message_tokens(plain)
        assert estimate_message_tokens(with_calls) > estimate_tokens("")


class TestRebuildAfterToolRound:
    @pytest.mark.asyncio
    async def test_second_call_rebuilt_within_budget(self, qwen_profile):
        budget = ContextBudget.from_profile(qwen_profile)
        builder = ContextBuilder(budget=budget)
        history = [LLMMessage(role="user", content="check this " + "x" * 3000)]
        first = builder.build(system_prompt="sys " + "s" * 2000,
                              conversation_messages=history)
        # Simulate one agentic round appended in memory.
        first.append(LLMMessage(role="assistant", content="", tool_calls=[_tc()]))
        first.append(LLMMessage(role="tool", content="result " + "r" * 3000,
                                tool_call_id="call-1", name="echo"))
        rebuilt = builder.build(system_prompt="sys " + "s" * 2000,
                                conversation_messages=[m for m in first if m.role != "system"])
        used = builder.last_build_summary["used_tokens"]
        assert used <= builder.last_build_summary["available_tokens"]
        assert_valid_tool_sequence(rebuilt)

    @pytest.mark.asyncio
    async def test_current_user_message_never_dropped(self, qwen_profile):
        budget = ContextBudget(total_tokens=512, response_reserve=128)
        builder = ContextBuilder(budget=budget)
        history = [LLMMessage(role="user", content=f"old {i} " + "x" * 500) for i in range(20)]
        history.append(LLMMessage(role="user", content="CURRENT REQUEST MARKER"))
        rebuilt = builder.build(system_prompt="sys", conversation_messages=history)
        assert any("CURRENT REQUEST MARKER" in (m.content or "") for m in rebuilt)


class TestOrchestratorMaxTokens:
    @pytest.mark.asyncio
    async def test_max_tokens_transmitted_every_call(self, qwen_profile):
        spy = SpyProvider([_tool_call_response(), _text_response("done!")])
        orch = Orchestrator(llm_provider=spy)
        resp = await orch.process_message(OrchestratorRequest(message="echo hi", device_id="test"))
        assert resp.response_text == "done!"
        assert len(spy.calls) == 2
        for call in spy.calls:
            assert call["max_tokens"] == qwen_profile.response_reserve == 1024
        # Second call carries the tool round and still fits the budget.
        available = qwen_profile.effective_budget - qwen_profile.response_reserve
        assert _prompt_tokens(spy.calls[1]) <= available
        assert_valid_tool_sequence(spy.calls[1]["messages"])

    @pytest.mark.asyncio
    async def test_streaming_uses_same_protection(self, qwen_profile):
        spy = SpyProvider([_tool_call_response(), _text_response("streamed!")])
        orch = Orchestrator(llm_provider=spy)
        from core.contracts.orchestrator import OrchestratorMessageType
        events = [e async for e in orch.stream_message(
            OrchestratorRequest(message="echo hi", device_id="test"))]
        assert events[-1].event_type == OrchestratorMessageType.DONE
        assert len(spy.calls) == 2
        for call in spy.calls:
            assert call["method"] == "generate_stream"
            assert call["max_tokens"] == 1024
        available = qwen_profile.effective_budget - qwen_profile.response_reserve
        assert _prompt_tokens(spy.calls[1]) <= available
        assert_valid_tool_sequence(spy.calls[1]["messages"])

    @pytest.mark.asyncio
    async def test_legacy_mode_passes_through(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CONTEXT_BUDGET_ENABLED", "false")
        reset_settings()
        spy = SpyProvider([_tool_call_response(), _text_response("done!")])
        orch = Orchestrator(llm_provider=spy)
        await orch.process_message(OrchestratorRequest(message="echo hi", device_id="test"))
        assert len(spy.calls) == 2
        for call in spy.calls:
            assert call["max_tokens"] is None
            assert sum(1 for m in call["messages"] if m.role == "system") == 1


class TestQwenRegression:
    @pytest.mark.asyncio
    async def test_qwen35_4b_profile_unchanged(self):
        profile = get_provider_profile("ollama", "qwen3.5:4b")
        assert profile.total_token_limit == 4096

    @pytest.mark.asyncio
    async def test_qwen35_scenario_stays_in_budget(self, qwen_profile, monkeypatch):
        """Reproduces the real incident: system + 28 tools + history + tool
        round on qwen3.5:4b (4096 total). The second LLM call must fit."""
        from tools.registry import get_tool_registry
        from tools import register_default_tools
        from core.llm.converters import tools_metadata_to_llm_defs

        registry = get_tool_registry()
        register_default_tools(registry)
        all_tools = tools_metadata_to_llm_defs(registry.list_tools())
        total_registered = len(all_tools)
        assert total_registered >= 20  # full default set (HA tools need SERVER role)

        spy = SpyProvider([_tool_call_response(), _text_response("ok")])
        orch = Orchestrator(llm_provider=spy)
        await orch.process_message(OrchestratorRequest(
            message="check system status " + "x" * 1500, device_id="test"))
        assert len(spy.calls) == 2
        second = spy.calls[1]
        available = qwen_profile.effective_budget - qwen_profile.response_reserve
        assert _prompt_tokens(second) <= available
        assert second["max_tokens"] == 1024
        assert_valid_tool_sequence(second["messages"])


class TestSelectionAndPolicy:
    @pytest.mark.asyncio
    async def test_tool_selection_still_applies(self, qwen_profile):
        spy = SpyProvider([_text_response("ok")])
        orch = Orchestrator(
            llm_provider=spy,
            tool_selector=ToolContextSelector(max_tools=5),
        )
        await orch.process_message(OrchestratorRequest(message="what time is it", device_id="t"))
        from tools.registry import get_tool_registry
        total = len(get_tool_registry().list_tools())
        assert total >= 20
        assert len(spy.calls) == 1
        assert spy.calls[0]["max_tokens"] == 1024
        assert len(spy.calls[0]["tools"]) <= 10  # max + fallback headroom
        assert len(spy.calls[0]["tools"]) < total

    @pytest.mark.asyncio
    async def test_policy_engine_remains_authority(self, qwen_profile):
        spy = SpyProvider([_tool_call_response(
            name="close_application", arguments={"name": "calc"}, call_id="call-9"),
            _text_response("unused")])
        orch = Orchestrator(llm_provider=spy)
        resp = await orch.process_message(OrchestratorRequest(
            message="close calc", device_id="t"))
        # YELLOW tool without confirmation: orchestrator must pause, never execute.
        assert resp.needs_confirmation is True
        assert len(spy.calls) == 1
        assert spy.calls[0]["max_tokens"] == 1024
