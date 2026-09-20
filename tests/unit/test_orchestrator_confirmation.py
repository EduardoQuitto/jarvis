"""Regression tests for the YELLOW/RED confirmation flow through the Orchestrator.

Covers the real-world failure: "Abra a calculadora" must pause for approval
(needs_confirmation=True + confirmation_id), never execute before approval,
execute only after genuine approval, and never report "Action completed."
when the tool actually failed.

subprocess.Popen is mocked so no real application ever launches.
"""

import pytest
from unittest.mock import patch

from core.contracts.enums import SecurityLevel
from core.contracts.llm import LLMResponse, LLMToolCall, LLMFunctionCall
from core.contracts.orchestrator import OrchestratorRequest
from core.llm.mock_provider import MockLLMProvider
from core.orchestrator.engine import Orchestrator
from tools.base import FunctionalTool


def _tool_call_response(tool_name, arguments, call_id="call-1"):
    return LLMResponse(
        content=None,
        tool_calls=[
            LLMToolCall(
                id=call_id,
                type="function",
                function=LLMFunctionCall(name=tool_name, arguments=arguments),
            )
        ],
        finish_reason="tool_calls",
    )


def _text_response(text):
    return LLMResponse(content=text, tool_calls=[], finish_reason="stop")


def _empty_response():
    return LLMResponse(content=None, tool_calls=[], finish_reason="stop")


def _make_orchestrator(responses):
    llm = MockLLMProvider()
    llm.set_responses(responses)
    return Orchestrator(llm_provider=llm), llm


@pytest.mark.asyncio
async def test_yellow_requires_confirmation_and_does_not_execute():
    """LLM calls launch_application -> needs_confirmation=True, tool untouched."""
    orch, _ = _make_orchestrator([_tool_call_response("launch_application", {"app_name": "calc"})])
    with patch("subprocess.Popen") as mock_popen:
        resp = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora do Windows.", device_id="test-device")
        )
    assert resp.needs_confirmation is True
    assert resp.confirmation_id  # non-empty
    assert "launch_application" in (resp.confirmation_details or "")
    mock_popen.assert_not_called()


@pytest.mark.asyncio
async def test_approved_confirmation_executes_yellow():
    """Genuine approval (cid + session) -> launch_application really executes."""
    orch, llm = _make_orchestrator([
        _tool_call_response("launch_application", {"app_name": "calc"}),
        _text_response("Calculadora aberta."),
    ])
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        )
        assert first.needs_confirmation is True

        second = await orch.process_message(
            OrchestratorRequest(
                message="sim, pode abrir",
                session_id=first.session_id,
                device_id="test-device",
                confirmation_id=first.confirmation_id,
                approved=True,
            )
        )
    assert second.needs_confirmation is False
    assert len(second.tool_calls_made) == 1
    assert second.tool_calls_made[0].success is True
    assert second.tool_calls_made[0].tool_name == "launch_application"
    mock_popen.assert_called_once()
    assert second.response_text == "Calculadora aberta."


@pytest.mark.asyncio
async def test_denied_confirmation_does_not_execute():
    """Denial -> tool never executes, denial reported."""
    orch, _ = _make_orchestrator([_tool_call_response("launch_application", {"app_name": "calc"})])
    with patch("subprocess.Popen") as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        )
        second = await orch.process_message(
            OrchestratorRequest(
                message="não, cancela",
                session_id=first.session_id,
                device_id="test-device",
                confirmation_id=first.confirmation_id,
                approved=False,
            )
        )
    mock_popen.assert_not_called()
    assert second.needs_confirmation is False
    assert "denied" in second.response_text


@pytest.mark.asyncio
async def test_failed_yellow_never_reports_action_completed():
    """Approved YELLOW tool that fails must not be reported as completed."""
    orch, llm = _make_orchestrator([
        _tool_call_response("launch_application", {"app_name": "calc"}),
        _empty_response(),  # LLM returns no summary text
    ])
    with patch("subprocess.Popen", side_effect=OSError("cannot launch here")) as mock_popen:
        first = await orch.process_message(
            OrchestratorRequest(message="Abra a calculadora.", device_id="test-device")
        )
        second = await orch.process_message(
            OrchestratorRequest(
                message="sim",
                session_id=first.session_id,
                device_id="test-device",
                confirmation_id=first.confirmation_id,
                approved=True,
            )
        )
    mock_popen.assert_called_once()  # approval really executed the tool...
    assert second.tool_calls_made[0].success is False  # ...which failed...
    assert second.response_text != "Action completed."  # ...and must say so
    assert "failed" in second.response_text.lower()


@pytest.mark.asyncio
async def test_green_tool_still_executes_freely():
    """GREEN tools execute without confirmation (no regression)."""
    llm = MockLLMProvider(auto_tool_calls=True)  # first call -> echo (GREEN)
    orch = Orchestrator(llm_provider=llm)
    resp = await orch.process_message(
        OrchestratorRequest(message="Check system status.", device_id="test-device")
    )
    assert resp.needs_confirmation is False
    assert resp.confirmation_id is None
    assert any(tc.success for tc in resp.tool_calls_made)


@pytest.mark.asyncio
async def test_red_cannot_be_confirmed_by_orchestrator_path():
    """RED: LLM/orchestrator path can never self-confirm; operator approval works."""
    from tools.registry import get_tool_registry
    from tools import register_default_tools
    from core.orchestrator.tool_executor import ToolExecutor

    async def _red_impl(**kwargs):
        return {"wiped": False}

    registry = get_tool_registry()
    register_default_tools(registry)
    registry.register(FunctionalTool(
        name="red_probe_tool",
        description="RED probe for tests (never destructive).",
        func=_red_impl,
        security_level=SecurityLevel.RED,
    ))

    # LLM requests the RED tool -> must pause for explicit approval
    orch, _ = _make_orchestrator([_tool_call_response("red_probe_tool", {})])
    first = await orch.process_message(
        OrchestratorRequest(message="Do the red thing.", device_id="test-device")
    )
    assert first.needs_confirmation is True
    assert first.confirmation_id

    # Direct LLM-path execution attempts stay denied (no bypass possible)
    executor = ToolExecutor()
    denied_orch = await executor.execute_tool_call("red_probe_tool", {}, source="orchestrator")
    assert denied_orch.success is False
    denied_op = await executor.execute_tool_call("red_probe_tool", {}, source="operator")
    assert denied_op.success is False  # unconfirmed operator call also denied

    # The appropriate flow (explicit approval + consume) executes via operator
    second = await orch.process_message(
        OrchestratorRequest(
            message="sim, autorizo",
            session_id=first.session_id,
            device_id="test-device",
            confirmation_id=first.confirmation_id,
            approved=True,
        )
    )
    assert second.tool_calls_made[0].success is True
