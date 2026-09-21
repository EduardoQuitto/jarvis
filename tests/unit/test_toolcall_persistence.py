"""Regression tests for tool-call persistence across restarts (Bug 3).

A complete agentic turn must survive as:
  user -> assistant(tool_calls) -> tool(result) -> assistant(final)
and the reloaded context must stay valid for OpenAI-compatible providers
(Ollama, Gemini): no orphan tool messages, every call id answered.
"""

import json

import pytest
from unittest.mock import patch

from core.contracts.llm import LLMMessage, LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.conversation.manager import ConversationManager
from core.llm.mock_provider import MockLLMProvider
from core.orchestrator.engine import Orchestrator
from tests.unit.tool_sequence_check import assert_valid_tool_sequence


def _tool_call_response(tool_name, arguments, call_id="call-1"):
    return LLMResponse(
        content=None,
        tool_calls=[LLMToolCall(id=call_id, type="function",
                                function=LLMFunctionCall(name=tool_name, arguments=arguments))],
        finish_reason="tool_calls",
    )


def _text_response(text):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop")


def _call(call_id, name="echo", arguments=None):
    return LLMToolCall(id=call_id, type="function",
                       function=LLMFunctionCall(name=name, arguments=arguments or {}))


def _assistant_with_calls(*calls):
    return LLMMessage(role="assistant", content="", tool_calls=list(calls))


def _tool_result(call_id, name="echo", content="ok"):
    return LLMMessage(role="tool", content=content, tool_call_id=call_id, name=name)


def _text(role, content):
    return LLMMessage(role=role, content=content)


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
    assert_valid_tool_sequence(window)


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
    # Approved flow persists as: user, assistant(tool_calls), tool(result),
    # assistant(final). The "[Action requires confirmation]" note is NOT a
    # persisted assistant message (it would break the sequence).
    assert roles == ["user", "assistant", "tool", "assistant"]

    assistants_with_calls = [m for m in history if m.tool_calls_json]
    assert len(assistants_with_calls) == 1, "assistant turn duplicated or lost"
    assert json.loads(assistants_with_calls[0].tool_calls_json)[0]["id"] == "call-1"

    tool_msgs = [m for m in history if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "call-1"

    window = await reloaded.get_context_window(first.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_denied_confirmation_closes_call_validly():
    llm = MockLLMProvider()
    llm.set_responses([_tool_call_response("launch_application", {"app_name": "calc"})])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen"):
        first = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        )
        second = await orch.process_message(
            OrchestratorRequest(message="não", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=False)
        )
        assert "denied" in second.response_text

    reloaded = ConversationManager()
    history = await reloaded.get_history(first.session_id)
    # Denied flow: user, assistant(tool_calls), tool(denial note), assistant(denied).
    # The pending call is answered exactly once — never left dangling.
    assert [m.role for m in history] == ["user", "assistant", "tool", "assistant"]
    assert history[2].tool_call_id == "call-1"
    assert "not executed" in (history[2].content or "")

    window = await reloaded.get_context_window(first.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_multi_tool_turn_survives_reload():
    llm = MockLLMProvider()
    llm.set_responses([
        LLMResponse(
            content=None,
            tool_calls=[_call("call-1", "echo", {"message": "a"}),
                        _call("call-2", "echo", {"message": "b"})],
            finish_reason="tool_calls",
        ),
        _text_response("both done"),
    ])
    orch = Orchestrator(llm_provider=llm)
    resp = await orch.process_message(
        OrchestratorRequest(message="echo twice", device_id="test-device")
    )
    assert len(resp.tool_calls_made) == 2

    reloaded = ConversationManager()
    history = await reloaded.get_history(resp.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [m.tool_call_id for m in history if m.role == "tool"] == ["call-1", "call-2"]

    window = await reloaded.get_context_window(resp.session_id)
    assert_valid_tool_sequence(window)


def test_validator_rejects_interleaved_assistant():
    with pytest.raises(AssertionError):
        assert_valid_tool_sequence([
            _text("user", "hi"),
            _assistant_with_calls(_call("call-1")),
            _text("assistant", "status note"),  # must not sit between call and result
            _tool_result("call-1"),
        ])


def test_validator_rejects_orphan_tool():
    with pytest.raises(AssertionError):
        assert_valid_tool_sequence([
            _text("user", "hi"),
            _tool_result("call-9"),
        ])


def test_validator_rejects_duplicate_and_missing_results():
    with pytest.raises(AssertionError):
        assert_valid_tool_sequence([
            _text("user", "hi"),
            _assistant_with_calls(_call("call-1")),
            _tool_result("call-1"),
            _tool_result("call-1"),  # answered twice
        ])
    with pytest.raises(AssertionError):
        assert_valid_tool_sequence([
            _text("user", "hi"),
            _assistant_with_calls(_call("call-1")),  # never answered
            _text("assistant", "done"),
        ])


def test_validator_accepts_pending_when_allowed():
    assert_valid_tool_sequence([
        _text("user", "hi"),
        _assistant_with_calls(_call("call-1")),
    ], allow_pending=True)
