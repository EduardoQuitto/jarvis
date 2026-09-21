"""Multi-tool confirmation turns (assistant with several tool_calls).

Covers: GREEN+GREEN, GREEN+YELLOW ordering both ways, approval executing the
whole turn, denial closing only its own call, full-history validation with
assert_valid_tool_sequence, and reload persistence. subprocess.Popen is
mocked so no real application ever launches.
"""

import pytest
from unittest.mock import patch

from core.contracts.llm import LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.conversation.manager import ConversationManager
from core.llm.mock_provider import MockLLMProvider
from core.orchestrator.engine import Orchestrator
from tests.unit.tool_sequence_check import assert_valid_tool_sequence


def _turn(*calls, summary="all done"):
    """One assistant turn with the given (tool_name, arguments, call_id) calls."""
    return LLMResponse(
        content=None,
        tool_calls=[LLMToolCall(id=cid, type="function",
                                function=LLMFunctionCall(name=name, arguments=args))
                    for name, args, cid in calls],
        finish_reason="tool_calls",
    )


def _text_response(text):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop")


def _reload_history(session_id):
    return ConversationManager().get_history(session_id)


@pytest.mark.asyncio
async def test_two_green_calls_both_execute():
    llm = MockLLMProvider()
    llm.set_responses([
        _turn(("echo", {"message": "a"}, "call-1"), ("echo", {"message": "b"}, "call-2")),
        _text_response("both echoed"),
    ])
    orch = Orchestrator(llm_provider=llm)
    resp = await orch.process_message(
        OrchestratorRequest(message="echo twice", device_id="test-device")
    )
    assert resp.needs_confirmation is False
    assert [r.tool_name for r in resp.tool_calls_made] == ["echo", "echo"]
    assert all(r.success for r in resp.tool_calls_made)

    history = await _reload_history(resp.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [m.tool_call_id for m in history if m.role == "tool"] == ["call-1", "call-2"]
    window = await ConversationManager().get_context_window(resp.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_green_then_yellow_pauses_and_resumes_whole_turn():
    llm = MockLLMProvider()
    llm.set_responses([
        _turn(("echo", {"message": "a"}, "call-1"),
              ("launch_application", {"app_name": "calc"}, "call-2")),
        _text_response("turn complete"),
    ])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="echo and open calc", device_id="test-device")
        )
        # GREEN ran, YELLOW paused the turn.
        assert first.needs_confirmation is True
        assert first.confirmation_id
        mock_popen.assert_not_called()

        second = await orch.process_message(
            OrchestratorRequest(message="sim", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=True)
        )
    # Approval executed the YELLOW call; GREEN is not re-executed.
    assert second.needs_confirmation is False
    assert [r.tool_name for r in second.tool_calls_made] == ["launch_application"]
    assert all(r.success for r in second.tool_calls_made)
    mock_popen.assert_called_once()

    history = await _reload_history(first.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [m.tool_call_id for m in history if m.role == "tool"] == ["call-1", "call-2"]
    window = await ConversationManager().get_context_window(first.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_yellow_then_green_continues_after_approval():
    llm = MockLLMProvider()
    llm.set_responses([
        _turn(("launch_application", {"app_name": "calc"}, "call-1"),
              ("echo", {"message": "opened"}, "call-2")),
        _text_response("turn complete"),
    ])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="open calc then echo", device_id="test-device")
        )
        assert first.needs_confirmation is True
        # GREEN sibling was NOT executed before approval.
        history = await _reload_history(first.session_id)
        assert [m.role for m in history] == ["user", "assistant"]

        second = await orch.process_message(
            OrchestratorRequest(message="sim", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=True)
        )
    # Resume executed the approved YELLOW AND continued with the GREEN sibling.
    assert [r.tool_name for r in second.tool_calls_made] == ["launch_application", "echo"]
    assert all(r.success for r in second.tool_calls_made)
    mock_popen.assert_called_once()

    history = await _reload_history(first.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    window = await ConversationManager().get_context_window(first.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_deny_yellow_still_runs_green_sibling():
    llm = MockLLMProvider()
    llm.set_responses([
        _turn(("launch_application", {"app_name": "calc"}, "call-1"),
              ("echo", {"message": "skipped launch"}, "call-2")),
    ])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="open calc then echo", device_id="test-device")
        )
        second = await orch.process_message(
            OrchestratorRequest(message="não", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=False)
        )
    # Denied tool never ran; GREEN sibling still ran through its own gate.
    mock_popen.assert_not_called()
    assert "denied" in second.response_text
    assert [r.tool_name for r in second.tool_calls_made] == ["echo"]
    assert all(r.success for r in second.tool_calls_made)

    history = await _reload_history(first.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    denied_note = [m for m in history if m.role == "tool"][0]
    assert denied_note.tool_call_id == "call-1"
    assert "not executed" in (denied_note.content or "")
    window = await ConversationManager().get_context_window(first.session_id)
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_second_confirmation_for_second_yellow():
    llm = MockLLMProvider()
    llm.set_responses([
        _turn(("launch_application", {"app_name": "calc"}, "call-1"),
              ("launch_application", {"app_name": "notepad"}, "call-2")),
        _text_response("both opened"),
    ])
    orch = Orchestrator(llm_provider=llm)
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="open calc and notepad", device_id="test-device")
        )
        assert first.needs_confirmation is True

        second = await orch.process_message(
            OrchestratorRequest(message="sim", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=first.confirmation_id, approved=True)
        )
        # Approving the first YELLOW pauses again on the second one —
        # without breaking the sequence.
        assert second.needs_confirmation is True
        assert second.confirmation_id != first.confirmation_id
        assert mock_popen.call_count == 1

        history = await _reload_history(first.session_id)
        assert [m.role for m in history] == ["user", "assistant", "tool"]
        window = await ConversationManager().get_context_window(first.session_id)
        assert_valid_tool_sequence(window, allow_pending=True)

        third = await orch.process_message(
            OrchestratorRequest(message="sim", session_id=first.session_id,
                                device_id="test-device",
                                confirmation_id=second.confirmation_id, approved=True)
        )
    assert third.needs_confirmation is False
    assert [r.tool_name for r in third.tool_calls_made] == ["launch_application"]
    assert mock_popen.call_count == 2

    history = await _reload_history(first.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "tool", "assistant"]
    window = await ConversationManager().get_context_window(first.session_id)
    assert_valid_tool_sequence(window)
