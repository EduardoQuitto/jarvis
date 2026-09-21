"""Regression tests for tool-call persistence across restarts (Bug 3).

A complete agentic turn must survive as:
  user -> assistant(tool_calls) -> tool(result) -> assistant(final)
and the reloaded context must stay valid for OpenAI-compatible providers
(Ollama, Gemini): no orphan tool messages, every call id answered.
"""

import json

import pytest
from unittest.mock import patch

from core.contracts.llm import LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.conversation.manager import ConversationManager
from core.llm.mock_provider import MockLLMProvider
from core.orchestrator.engine import Orchestrator


def _tool_call_response(tool_name, arguments, call_id="call-1"):
    return LLMResponse(
        content=None,
        tool_calls=[LLMToolCall(id=call_id, type="function",
                                function=LLMFunctionCall(name=tool_name, arguments=arguments))],
        finish_reason="tool_calls",
    )


def _text_response(text):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop")


def _assert_valid_openai_sequence(messages):
    """Every tool must answer a preceding assistant call; no orphan tools."""
    answered = set()
    pending = {}
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            for tc in m.tool_calls:
                assert tc.id not in pending, f"duplicate call id {tc.id}"
                pending[tc.id] = tc.function.name
        elif m.role == "tool":
            assert m.tool_call_id, "tool message without tool_call_id"
            assert m.tool_call_id in pending, f"orphan tool result for {m.tool_call_id}"
            answered.add(m.tool_call_id)
    assert set(pending) == answered, f"unanswered calls: {set(pending) - answered}"


@pytest.mark.asyncio
async def test_full_turn_survives_reload_in_order():
    llm = MockLLMProvider()
    llm.set_responses([
        _tool_call_response("echo", {"message": "hi"}),
        _text_response("done!"),
    ])
    orch = Orchestrator(llm_provider=llm)
    resp = await orch.process_message(
        OrchestratorRequest(message="say hi", device_id="test-device")
    )

    # Simulate a restart: brand-new manager over the same database file.
    reloaded = ConversationManager()
    history = await reloaded.get_history(resp.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "assistant"]

    assistant_tc = history[1]
    assert assistant_tc.tool_calls_json, "assistant tool calls were not persisted"
    persisted_calls = json.loads(assistant_tc.tool_calls_json)
    assert persisted_calls[0]["id"] == "call-1"
    assert persisted_calls[0]["function"]["name"] == "echo"

    tool_msg = history[2]
    assert tool_msg.tool_call_id == "call-1"
    assert tool_msg.name == "echo"
    assert history[3].content == "done!"

    # Reloaded LLM context is provider-valid (no orphans, all calls answered).
    window = await reloaded.get_context_window(resp.session_id)
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    _assert_valid_openai_sequence(window)


@pytest.mark.asyncio
async def test_confirmation_flow_persists_without_duplicates():
    llm = MockLLMProvider()
    llm.set_responses([
        _tool_call_response("launch_application", {"app_name": "calc"}),
        _text_response("Calculadora aberta."),
    ])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen"):
        first = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        )
        assert first.needs_confirmation is True
        second = await orch.process_message(
            OrchestratorRequest(message="sim", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=True)
        )
        assert second.tool_calls_made[0].success is True

    reloaded = ConversationManager()
    history = await reloaded.get_history(first.session_id)
    roles = [m.role for m in history]
    # user, assistant(tool_calls), assistant(status note), tool(result), assistant(final)
    assert roles == ["user", "assistant", "assistant", "tool", "assistant"]

    assistants_with_calls = [m for m in history if m.tool_calls_json]
    assert len(assistants_with_calls) == 1, "assistant turn duplicated or lost"
    assert json.loads(assistants_with_calls[0].tool_calls_json)[0]["id"] == "call-1"

    tool_msgs = [m for m in history if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "call-1"

    window = await reloaded.get_context_window(first.session_id)
    _assert_valid_openai_sequence(window)
