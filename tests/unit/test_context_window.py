"""Regression tests for the sliding context window (Bug 2).

The window must return the most RECENT messages in chronological order,
never start with an orphan `tool` message, and stay compatible with
OpenAI-compatible providers (Ollama, Gemini).
"""

import json

import pytest

from core.conversation.manager import ConversationManager
from core.contracts.llm import LLMToolCall, LLMFunctionCall


@pytest.mark.asyncio
async def test_window_returns_recent_tail_in_order():
    manager = ConversationManager(max_context_messages=40)
    session_id = await manager.create_session(title="long chat")
    for i in range(45):
        await manager.append_message(session_id, "user", f"msg-{i:02d}")

    history = await manager.get_history(session_id, limit=40)
    assert len(history) == 40
    assert [m.content for m in history] == [f"msg-{i:02d}" for i in range(5, 45)]


@pytest.mark.asyncio
async def test_window_never_starts_with_orphan_tool():
    manager = ConversationManager(max_context_messages=10)
    session_id = await manager.create_session(title="tool sequence")

    await manager.append_message(session_id, "user", "do two things")
    tool_calls = [
        LLMToolCall(id="call-a", type="function",
                    function=LLMFunctionCall(name="echo", arguments={"message": "a"})).model_dump(),
        LLMToolCall(id="call-b", type="function",
                    function=LLMFunctionCall(name="echo", arguments={"message": "b"})).model_dump(),
    ]
    await manager.append_message(session_id, "assistant", "",
                                 tool_calls_json=json.dumps(tool_calls))
    await manager.append_message(session_id, "tool", "{'echo': 'a'}",
                                 tool_call_id="call-a", name="echo")
    await manager.append_message(session_id, "tool", "{'echo': 'b'}",
                                 tool_call_id="call-b", name="echo")
    await manager.append_message(session_id, "assistant", "done")

    # limit=3 cuts [user, assistant(tc)] off, leaving [tool, tool, assistant]
    history = await manager.get_history(session_id, limit=3)
    assert history, "window must not collapse to empty"
    assert history[0].role != "tool", "orphan tool message at window start"
    assert [m.role for m in history] == ["assistant"]

    window = await manager.get_context_window(session_id)
    assert window[0].role != "tool"


@pytest.mark.asyncio
async def test_tool_sequence_survives_intact_when_fitting():
    manager = ConversationManager(max_context_messages=10)
    session_id = await manager.create_session(title="intact sequence")

    await manager.append_message(session_id, "user", "echo hi")
    tool_calls = [LLMToolCall(id="call-1", type="function",
                              function=LLMFunctionCall(
                                  name="echo", arguments={"message": "hi"})).model_dump()]
    await manager.append_message(session_id, "assistant", "",
                                 tool_calls_json=json.dumps(tool_calls))
    await manager.append_message(session_id, "tool", "{'echo': 'hi'}",
                                 tool_call_id="call-1", name="echo")
    await manager.append_message(session_id, "assistant", "done!")

    window = await manager.get_context_window(session_id)
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    assert window[1].tool_calls is not None
    assert window[1].tool_calls[0].id == "call-1"
    assert window[2].tool_call_id == "call-1"
    assert window[2].name == "echo"


@pytest.mark.asyncio
async def test_window_roles_are_provider_compatible():
    manager = ConversationManager(max_context_messages=40)
    session_id = await manager.create_session(title="compat")
    for i in range(45):
        role = "assistant" if i % 2 else "user"
        await manager.append_message(session_id, role, f"msg-{i}")

    window = await manager.get_context_window(session_id)
    assert len(window) == 40
    assert all(m.role in ("user", "assistant", "tool", "system") for m in window)
    assert all(m.tool_call_id is None or m.role == "tool" for m in window)
