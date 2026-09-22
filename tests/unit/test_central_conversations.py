"""Tests for central conversations: SERVER API + ConversationManager backend.

SERVER API runs in-process (ASGITransport, isolated tmp DB).
Manager tests use a stub central backend, plus one MockTransport-backed
integration proving the settings wiring. No real network.
"""

import json

import httpx
import pytest

from core.config import get_settings, reset_settings
from core.conversation.manager import ConversationManager
from core.network.central_state_client import CentralStateClient, CentralStateError
from core.network.node_client import RemoteNodeClient


class _StubCentral:
    """In-memory central backend honoring the CentralStateClient conversation API."""

    def __init__(self, fail_with=None):
        self.sessions = {}
        self.fail_with = fail_with
        self.calls = []

    def _maybe_fail(self, operation):
        if self.fail_with is not None:
            raise self.fail_with

    async def create_conversation(self, conversation_id, title=None, device_id=None):
        self._maybe_fail("create_conversation")
        self.calls.append(("create", conversation_id))
        self.sessions[conversation_id] = {"id": conversation_id, "title": title,
                                          "device_id": device_id, "messages": []}
        return {"id": conversation_id, "created": True}

    async def list_conversations(self, limit=20):
        self._maybe_fail("list_conversations")
        return [{"id": sid, "title": s["title"], "device_id": s["device_id"],
                 "message_count": len(s["messages"])}
                for sid, s in list(self.sessions.items())[:limit]]

    async def get_conversation(self, conversation_id):
        self._maybe_fail("get_conversation")
        s = self.sessions.get(conversation_id)
        if s is None:
            return None
        return {"id": conversation_id, "title": s["title"],
                "device_id": s["device_id"], "message_count": len(s["messages"])}

    async def get_messages(self, conversation_id, limit=50):
        self._maybe_fail("get_messages")
        return self.sessions[conversation_id]["messages"][-limit:]

    async def append_message(self, conversation_id, role, content,
                             tool_calls_json=None, tool_call_id=None, name=None):
        self._maybe_fail("append_message")
        self.calls.append(("append", conversation_id, role))
        self.sessions[conversation_id]["messages"].append({
            "id": len(self.sessions[conversation_id]["messages"]) + 1,
            "role": role, "content": content, "tool_calls_json": tool_calls_json,
            "tool_call_id": tool_call_id, "name": name,
        })
        return {"stored": True, "conversation_id": conversation_id}


def _manager_with_stub(**kwargs):
    stub = _StubCentral(**kwargs)
    return ConversationManager(central_state=stub), stub


@pytest.mark.asyncio
async def test_central_create_append_read():
    manager, stub = _manager_with_stub()
    session_id = await manager.create_session(title="central flow")
    assert ("create", session_id) in stub.calls
    await manager.append_message(session_id, "user", "hello")
    await manager.append_message(session_id, "assistant", "hi")
    history = await manager.get_history(session_id)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "hello"


@pytest.mark.asyncio
async def test_central_tool_sequence_roundtrip():
    manager, stub = _manager_with_stub()
    session_id = "sess-seq-1"
    await stub.create_conversation(session_id)
    manager = ConversationManager(central_state=stub)
    tool_calls = [{"id": "call-1", "type": "function",
                   "function": {"name": "echo", "arguments": {"message": "hi"}}}]
    await manager.append_message(session_id, "user", "echo hi")
    await manager.append_message(session_id, "assistant", "", tool_calls_json=json.dumps(tool_calls))
    await manager.append_message(session_id, "tool", "{'echo': 'hi'}",
                                 tool_call_id="call-1", name="echo")
    await manager.append_message(session_id, "assistant", "done")
    window = await manager.get_context_window(session_id)
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    assert window[1].tool_calls is not None and window[1].tool_calls[0].id == "call-1"
    assert window[2].tool_call_id == "call-1"


@pytest.mark.asyncio
async def test_central_required_raises_explicitly():
    manager, _ = _manager_with_stub(
        fail_with=CentralStateError("down", kind="connection"))
    import os
    os.environ["JARVIS_CENTRAL_STATE_REQUIRED"] = "true"
    try:
        reset_settings()
        with pytest.raises(CentralStateError) as exc_info:
            await manager.get_history("sess-x")
        assert "required" in str(exc_info.value).lower()
    finally:
        del os.environ["JARVIS_CENTRAL_STATE_REQUIRED"]
        reset_settings()


@pytest.mark.asyncio
async def test_central_failure_falls_back_local_when_not_required(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_REQUIRED", "false")
    reset_settings()
    manager, _ = _manager_with_stub(
        fail_with=CentralStateError("down", kind="connection"))
    session_id = await manager.create_session(title="fallback")
    await manager.append_message(session_id, "user", "local hello")
    history = await manager.get_history(session_id)
    assert [m.role for m in history] == ["user"]
    assert history[0].content == "local hello"


@pytest.mark.asyncio
async def test_manager_uses_central_from_settings(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/conversations/":
            return httpx.Response(200, json={"id": "sess-s", "created": True})
        if request.method == "POST" and request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"stored": True})
        if request.method == "GET" and request.url.path.endswith("/messages"):
            return httpx.Response(200, json=[{"id": 1, "role": "user", "content": "via server",
                                              "tool_calls_json": None, "tool_call_id": None, "name": None}])
        return httpx.Response(404, json={"detail": "not found"})

    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "true")
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "test-key")
    reset_settings()

    transport = httpx.MockTransport(handler)
    client = RemoteNodeClient(base_url="http://simulated-server:8000", api_key="test-key",
                              timeout=5.0, transport=transport)
    manager = ConversationManager(central_state=CentralStateClient(client=client))
    history = await manager.get_history("sess-s")
    assert [m.role for m in history] == ["user"]
    assert history[0].content == "via server"


@pytest.mark.asyncio
async def test_manager_disabled_stays_local(monkeypatch):
    monkeypatch.setenv("JARVIS_CENTRAL_STATE_ENABLED", "false")
    reset_settings()
    manager = ConversationManager()
    assert manager._get_central() is None
    session_id = await manager.create_session(title="local")
    await manager.append_message(session_id, "user", "hi")
    assert [m.role for m in await manager.get_history(session_id)] == ["user"]


# --- SERVER conversations API (in-process, isolated tmp DB) ---

@pytest.mark.asyncio
async def test_session_survives_manager_restart():
    """CORE restart: a fresh manager over the same central state keeps history."""
    manager1, stub = _manager_with_stub()
    session_id = await manager1.create_session(title="restartable")
    await manager1.append_message(session_id, "user", "remember this")
    del manager1  # simulate CORE restart: all RAM state gone

    manager2 = ConversationManager(central_state=stub)
    history = await manager2.get_history(session_id)
    assert [m.role for m in history] == ["user"]
    assert history[0].content == "remember this"
    info = await manager2.get_session_info(session_id)
    assert info is not None and info.id == session_id
    sessions = await manager2.list_sessions()
    assert any(s.id == session_id for s in sessions)


@pytest.mark.asyncio
async def test_orchestrator_turn_over_central_state_stays_valid():
    from core.contracts.llm import LLMResponse, LLMToolCall, LLMFunctionCall
    from core.contracts.orchestrator import OrchestratorRequest
    from core.llm.mock_provider import MockLLMProvider
    from core.orchestrator.engine import Orchestrator
    from tests.unit.tool_sequence_check import assert_valid_tool_sequence

    llm = MockLLMProvider()
    llm.set_responses([
        LLMResponse(content=None, tool_calls=[LLMToolCall(
            id="call-1", type="function",
            function=LLMFunctionCall(name="echo", arguments={"message": "hi"}))],
            finish_reason="tool_calls"),
        LLMResponse(content="done!", tool_calls=[], finish_reason="stop"),
    ])
    manager, stub = _manager_with_stub()
    orch = Orchestrator(llm_provider=llm, conversation_manager=manager)
    resp = await orch.process_message(
        OrchestratorRequest(message="say hi", device_id="test-device"))

    reloaded = ConversationManager(central_state=stub)
    window = await reloaded.get_context_window(resp.session_id)
    assert [m.role for m in window] == ["user", "assistant", "tool", "assistant"]
    assert_valid_tool_sequence(window)


@pytest.mark.asyncio
async def test_conversations_api_crud():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/conversations/",
                                     json={"conversation_id": "sess-api-1", "title": "t"},
                                     headers=headers)).json()
        assert created["created"] is True

        for role, content in [("user", "hello"), ("assistant", "hi")]:
            stored = (await client.post("/api/conversations/sess-api-1/messages",
                                        json={"role": role, "content": content},
                                        headers=headers)).json()
            assert stored["stored"] is True

        messages = (await client.get("/api/conversations/sess-api-1/messages",
                                     headers=headers)).json()
        assert [m["role"] for m in messages] == ["user", "assistant"]

        info = (await client.get("/api/conversations/sess-api-1", headers=headers)).json()
        assert info["message_count"] == 2

        listed = (await client.get("/api/conversations/", headers=headers)).json()
        assert any(c["id"] == "sess-api-1" for c in listed)

        missing = await client.get("/api/conversations/nope", headers=headers)
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_conversations_api_preserves_tool_sequence():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    tool_calls = json.dumps([{"id": "call-1", "type": "function",
                              "function": {"name": "echo", "arguments": {"message": "hi"}}}])
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/conversations/",
                          json={"conversation_id": "sess-api-seq"}, headers=headers)
        await client.post("/api/conversations/sess-api-seq/messages",
                          json={"role": "user", "content": "echo hi"}, headers=headers)
        await client.post("/api/conversations/sess-api-seq/messages",
                          json={"role": "assistant", "content": "",
                                "tool_calls_json": tool_calls}, headers=headers)
        await client.post("/api/conversations/sess-api-seq/messages",
                          json={"role": "tool", "content": "ok",
                                "tool_call_id": "call-1", "name": "echo"}, headers=headers)
        messages = (await client.get("/api/conversations/sess-api-seq/messages",
                                     headers=headers)).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert json.loads(messages[1]["tool_calls_json"])[0]["id"] == "call-1"
    assert messages[2]["tool_call_id"] == "call-1"
