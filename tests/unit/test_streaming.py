"""Tests for Phase 11 streaming (engine.stream_message + POST /api/chat/stream).

A. plain text streaming (deltas + done, concat == full text)
B. streaming through a real IntelligenceRouter
C. streaming with a tool call (tool_call/tool_result/final text, valid history)
D. YELLOW tool pauses with waiting_confirmation, tool untouched
E. approval resumes via a second stream and executes
F. provider failure surfaces as error + done (never silent, never raises)
G. client disconnect cancels cleanly with no orphan tasks
H. /api/chat/send untouched + /stream serves valid SSE frames
"""

import asyncio
import json

import pytest
from unittest.mock import patch

from core.contracts.llm import LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.conversation.manager import ConversationManager
from core.llm.mock_provider import MockLLMProvider
from core.llm.registry import ProviderRegistry
from core.llm.router import IntelligenceRouter
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


async def _collect(agen):
    return [event async for event in agen]


def _kinds(events):
    return [e.event_type.value.lower() for e in events]


@pytest.mark.asyncio
async def test_simple_text_streaming_deltas_and_done():
    text = "Olá Eduardo, como posso ajudar você hoje?"
    llm = MockLLMProvider()
    llm.set_responses([_text_response(text)])
    orch = Orchestrator(llm_provider=llm)

    events = await _collect(orch.stream_message(
        OrchestratorRequest(message="oi", device_id="test-device")
    ))
    kinds = _kinds(events)
    assert kinds[0] == "start"
    assert kinds[1] == "thinking"
    assert kinds[-1] == "done"
    deltas = [e.data["text"] for e in events if e.event_type.value == "TEXT_DELTA"]
    assert len(deltas) > 1  # genuinely chunked, not one blob
    assert "".join(deltas) == text
    assert events[-1].data["response_text"] == text


@pytest.mark.asyncio
async def test_streaming_through_real_router():
    registry = ProviderRegistry()
    registry.register("mock", MockLLMProvider(default_text="via router"), priority=1.0)
    orch = Orchestrator(router=IntelligenceRouter(registry=registry))

    events = await _collect(orch.stream_message(
        OrchestratorRequest(message="oi", device_id="test-device")
    ))
    assert _kinds(events)[-1] == "done"
    deltas = [e.data["text"] for e in events if e.event_type.value == "TEXT_DELTA"]
    assert "".join(deltas) == "via router"


@pytest.mark.asyncio
async def test_streaming_with_tool_call():
    llm = MockLLMProvider()
    llm.set_responses([
        _tool_call_response("echo", {"message": "hi"}),
        _text_response("echoed!"),
    ])
    orch = Orchestrator(llm_provider=llm)

    events = await _collect(orch.stream_message(
        OrchestratorRequest(message="echo hi", device_id="test-device")
    ))
    kinds = _kinds(events)
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert kinds[-1] == "done"
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("done")

    call_ev = next(e for e in events if e.event_type.value == "TOOL_CALL")
    assert call_ev.data["tool_name"] == "echo"
    result_ev = next(e for e in events if e.event_type.value == "TOOL_RESULT")
    assert result_ev.data["success"] is True

    final_text = "".join(e.data["text"] for e in events if e.event_type.value == "TEXT_DELTA")
    assert final_text == "echoed!"

    window = await ConversationManager().get_context_window(events[0].data["session_id"])
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_streaming_yellow_pauses_with_confirmation():
    llm = MockLLMProvider()
    llm.set_responses([_tool_call_response("launch_application", {"app_name": "calc"})])
    orch = Orchestrator(llm_provider=llm)

    with patch("subprocess.Popen") as mock_popen:
        events = await _collect(orch.stream_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        ))
    kinds = _kinds(events)
    assert "waiting_confirmation" in kinds
    assert kinds[-1] == "done"
    assert "tool_result" not in kinds  # never executed before approval
    mock_popen.assert_not_called()

    confirm_ev = next(e for e in events if e.event_type.value == "WAITING_CONFIRMATION")
    assert confirm_ev.data["confirmation_id"]
    assert confirm_ev.data["tool_name"] == "launch_application"
    assert confirm_ev.data["security_level"] == "YELLOW"
    assert confirm_ev.data["reason"]
    done_ev = events[-1]
    assert done_ev.data["needs_confirmation"] is True


@pytest.mark.asyncio
async def test_streaming_resume_after_approval():
    llm = MockLLMProvider()
    llm.set_responses([
        _tool_call_response("launch_application", {"app_name": "calc"}),
        _text_response("Calculadora aberta."),
    ])
    orch = Orchestrator(llm_provider=llm)

    with patch("subprocess.Popen") as mock_popen:
        first = await _collect(orch.stream_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        ))
        cid = next(e for e in first if e.event_type.value == "WAITING_CONFIRMATION").data["confirmation_id"]
        session_id = first[0].data["session_id"]

        second = await _collect(orch.stream_message(
            OrchestratorRequest(message="sim", session_id=session_id, device_id="test-device",
                                confirmation_id=cid, approved=True)
        ))
    mock_popen.assert_called_once()
    kinds = _kinds(second)
    assert "tool_result" in kinds
    assert kinds[-1] == "done"
    result_ev = next(e for e in second if e.event_type.value == "TOOL_RESULT")
    assert result_ev.data["success"] is True
    assert "".join(e.data["text"] for e in second if e.event_type.value == "TEXT_DELTA") == "Calculadora aberta."

    window = await ConversationManager().get_context_window(session_id)
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_streaming_provider_failure_is_explicit():
    registry = ProviderRegistry()  # no providers at all
    orch = Orchestrator(router=IntelligenceRouter(registry=registry))

    events = await _collect(orch.stream_message(
        OrchestratorRequest(message="oi", device_id="test-device")
    ))
    kinds = _kinds(events)
    assert "error" in kinds
    assert kinds[-1] == "done"
    error_ev = next(e for e in events if e.event_type.value == "ERROR")
    assert error_ev.data["message"]


@pytest.mark.asyncio
async def test_streaming_cancel_is_clean():
    llm = MockLLMProvider()
    llm.set_responses([_text_response("0123456789" * 20)])
    orch = Orchestrator(llm_provider=llm)

    stream = orch.stream_message(OrchestratorRequest(message="oi", device_id="test-device"))
    first = await stream.__anext__()
    assert first.event_type.value == "START"
    second = await stream.__anext__()
    assert second.event_type.value == "THINKING"
    await stream.aclose()  # client disconnect: must not raise
    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    await asyncio.sleep(0)
    # The streaming path creates no background tasks of its own.
    ours = [t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
            and t.get_name().startswith("jarvis-")]
    assert ours == []


def _mock_backed_app():
    from server.app import create_app
    import server.routers.chat as chat_module
    llm = MockLLMProvider(default_text="send ok")
    chat_module._orchestrator = Orchestrator(llm_provider=llm)
    return create_app()


@pytest.mark.asyncio
async def test_chat_send_still_works():
    from httpx import AsyncClient, ASGITransport
    from core.config import get_settings

    app = _mock_backed_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/send", json={"message": "oi"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["needs_confirmation"] is False
    assert body["response_text"] == "send ok"


@pytest.mark.asyncio
async def test_chat_stream_serves_valid_sse():
    from httpx import AsyncClient, ASGITransport
    from core.config import get_settings

    app = _mock_backed_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/chat/stream", json={"message": "oi"}, headers=headers) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            raw = await response.aread()
    text = raw.decode("utf-8")
    assert text.endswith("\n\n")
    frames = [f for f in text.split("\n\n") if f.strip()]
    assert len(frames) >= 3
    kinds = []
    for frame in frames:
        lines = frame.split("\n")
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        kinds.append(lines[0][len("event: "):])
        json.loads(lines[1][len("data: "):])  # every payload is valid JSON
    assert kinds[0] == "start"
    assert "thinking" in kinds
    assert "text_delta" in kinds
    assert kinds[-1] == "done"
