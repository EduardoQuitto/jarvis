"""Tests for central confirmations: SQLite store, SERVER API, manager backend.

SQLite tests run against an isolated tmp database. API tests run in-process
(ASGITransport). Manager tests use MockTransport-backed central state.
No real network.
"""

import time

import httpx
import pytest

from core.config import get_settings, reset_settings
from core.network.central_state_client import CentralStateClient
from core.network.node_client import RemoteNodeClient
from core.orchestrator.confirmation import ConfirmationManager
from memory.sqlite_provider import SQLiteMemoryProvider


def _confirmation_payload(cid="confirm-1", session_id="sess-1"):
    return {
        "confirmation_id": cid,
        "tool_name": "launch_application",
        "arguments": {"app_name": "calc"},
        "security_level": "YELLOW",
        "reason": "needs approval",
        "session_id": session_id,
        "call_id": "call-1",
        "remaining_calls": [{"tool_name": "echo", "arguments": {"message": "hi"}, "call_id": "call-2"}],
        "timeout_seconds": 300.0,
    }


# --- SQLite store ---

@pytest.mark.asyncio
async def test_sqlite_confirmation_lifecycle(tmp_path):
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "c.db"))
    await mem.create_confirmation(**_confirmation_payload_kwargs())
    row = await mem.get_confirmation("confirm-1")
    assert row["tool_name"] == "launch_application"
    assert row["consumed"] == 0

    assert await mem.resolve_confirmation("confirm-1", approved=True, now=time.time()) is True
    # Second resolve is rejected (single-use lifecycle starts at resolve)
    assert await mem.resolve_confirmation("confirm-1", approved=True, now=time.time()) is False

    claimed = await mem.consume_confirmation("confirm-1", session_id="sess-1", now=time.time())
    assert claimed is not None and claimed["consumed"] == 1
    # Replay is blocked
    assert await mem.consume_confirmation("confirm-1", session_id="sess-1", now=time.time()) is None


def _confirmation_payload_kwargs(cid="confirm-1", session_id="sess-1"):
    import json
    payload = _confirmation_payload(cid, session_id)
    return {
        "confirmation_id": payload["confirmation_id"],
        "tool_name": payload["tool_name"],
        "arguments_json": json.dumps(payload["arguments"]),
        "security_level": payload["security_level"],
        "reason": payload["reason"],
        "session_id": payload["session_id"],
        "call_id": payload["call_id"],
        "remaining_calls_json": json.dumps(payload["remaining_calls"]),
        "timeout_seconds": payload["timeout_seconds"],
    }


@pytest.mark.asyncio
async def test_sqlite_consume_rejects_unresolved_session_mismatch_expired(tmp_path):
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "c.db"))
    await mem.create_confirmation(**_confirmation_payload_kwargs("cid-a", "sess-a"))
    # Unresolved cannot be consumed
    assert await mem.consume_confirmation("cid-a", session_id="sess-a", now=time.time()) is None
    # Missing id
    assert await mem.consume_confirmation("nope", session_id="sess-a", now=time.time()) is None
    await mem.resolve_confirmation("cid-a", approved=True, now=time.time())
    # Cross-session misuse blocked
    assert await mem.consume_confirmation("cid-a", session_id="sess-B", now=time.time()) is None

    await mem.create_confirmation(**_confirmation_payload_kwargs("cid-b", "sess-b"))
    await mem.resolve_confirmation("cid-b", approved=False, now=time.time())
    claimed = await mem.consume_confirmation("cid-b", session_id="sess-b", now=time.time())
    assert claimed is not None and not claimed["approved"]

    # Expired records cannot be resolved or consumed
    old_kwargs = _confirmation_payload_kwargs("cid-c", "sess-c")
    old_kwargs["created_at"] = time.time() - 1000.0
    old_kwargs["timeout_seconds"] = 10.0
    await mem.create_confirmation(**old_kwargs)
    assert await mem.resolve_confirmation("cid-c", approved=True, now=time.time()) is False


@pytest.mark.asyncio
async def test_sqlite_pending_and_cleanup(tmp_path):
    mem = SQLiteMemoryProvider(db_path=str(tmp_path / "c.db"))
    await mem.create_confirmation(**_confirmation_payload_kwargs("cid-1", "sess-1"))
    await mem.create_confirmation(**_confirmation_payload_kwargs("cid-2", "sess-1"))
    await mem.resolve_confirmation("cid-1", approved=True, now=time.time())
    pending = await mem.list_pending_confirmations(now=time.time())
    assert [r["confirmation_id"] for r in pending] == ["cid-2"]
    await mem.consume_confirmation("cid-1", session_id="sess-1", now=time.time())
    assert await mem.cleanup_confirmations(now=time.time()) == 1
    assert await mem.get_confirmation("cid-1") is None
    assert await mem.get_confirmation("cid-2") is not None


# --- SERVER confirmations API ---

def _api_client(app):
    from httpx import AsyncClient, ASGITransport
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), headers


@pytest.mark.asyncio
async def test_confirmations_api_full_flow():
    from server.app import create_app

    app = create_app()
    client, headers = _api_client(app)
    async with client:
        created = (await client.post("/api/confirmations/", json=_confirmation_payload(),
                                     headers=headers)).json()
        assert created["created"] is True

        # Unresolved consume is rejected
        denied = await client.post("/api/confirmations/confirm-1/consume",
                                   json={"session_id": "sess-1"}, headers=headers)
        assert denied.status_code == 409

        resolved = (await client.post("/api/confirmations/confirm-1/resolve",
                                      json={"approved": True}, headers=headers)).json()
        assert resolved["approved"] is True

        # Cross-session consume rejected
        wrong = await client.post("/api/confirmations/confirm-1/consume",
                                  json={"session_id": "sess-X"}, headers=headers)
        assert wrong.status_code == 409

        claimed = (await client.post("/api/confirmations/confirm-1/consume",
                                     json={"session_id": "sess-1"}, headers=headers)).json()
        assert claimed["approved"] is True
        assert claimed["tool_name"] == "launch_application"
        assert claimed["arguments"] == {"app_name": "calc"}
        assert claimed["remaining_calls"] == [
            {"tool_name": "echo", "arguments": {"message": "hi"}, "call_id": "call-2"}]

        # Replay blocked
        replay = await client.post("/api/confirmations/confirm-1/consume",
                                   json={"session_id": "sess-1"}, headers=headers)
        assert replay.status_code == 409

        pending = (await client.get("/api/confirmations/pending", headers=headers)).json()
        assert pending == []

        # Duplicate create rejected
        dup = await client.post("/api/confirmations/", json=_confirmation_payload(),
                                headers=headers)
        assert dup.status_code == 409

        missing = await client.get("/api/confirmations/nope", headers=headers)
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_confirmations_api_denial_and_expiry():
    from server.app import create_app

    app = create_app()
    client, headers = _api_client(app)
    async with client:
        await client.post("/api/confirmations/", json=_confirmation_payload("cid-d", "sess-d"),
                          headers=headers)
        await client.post("/api/confirmations/cid-d/resolve",
                          json={"approved": False}, headers=headers)
        claimed = (await client.post("/api/confirmations/cid-d/consume",
                                     json={"session_id": "sess-d"}, headers=headers)).json()
        assert claimed["approved"] is False

        await client.post("/api/confirmations/", json=_confirmation_payload("cid-e", "sess-e"),
                          headers=headers)
        # Force expiry by backdating through a second create is impossible;
        # expire via cleanup path instead: create already-expired directly in DB
        from server.routers import confirmations as confirmations_router
        mem = confirmations_router._get_memory()
        import json as _json
        await mem.create_confirmation(
            confirmation_id="cid-old", tool_name="echo", arguments_json="{}",
            created_at=time.time() - 1000.0, timeout_seconds=10.0)
        cleaned = (await client.post("/api/confirmations/cleanup", headers=headers)).json()
        assert cleaned["removed"] >= 1


@pytest.mark.asyncio
async def test_confirmations_api_requires_auth():
    from server.app import create_app
    from httpx import AsyncClient, ASGITransport

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/confirmations/pending")
        assert response.status_code in (401, 403)


# --- ConfirmationManager with central backend ---

def _central_manager(handler):
    transport = httpx.MockTransport(handler)
    client = RemoteNodeClient(base_url="http://testserver", api_key="k",
                              timeout=5.0, transport=transport)
    manager = ConfirmationManager(central_state=CentralStateClient(client=client))
    return manager


@pytest.mark.asyncio
async def test_manager_central_request_approve_consume():
    import json as _json
    store = {}
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        if request.method == "POST" and request.url.path == "/api/confirmations/":
            body = _json.loads(request.content.decode())
            seen["create"] = body
            store[body["confirmation_id"]] = body
            return httpx.Response(200, json={"confirmation_id": body["confirmation_id"], "created": True})
        cid = parts[3] if len(parts) > 3 else ""
        if request.url.path.endswith("/resolve"):
            return httpx.Response(200, json={"confirmation_id": cid, "approved": True})
        if request.url.path.endswith("/consume"):
            if store.get(cid, {}).get("consumed"):
                return httpx.Response(409, json={"detail": "already consumed"})
            record = dict(store[cid])
            record.update({"approved": True, "resolved_at": 1.0, "consumed": 1})
            store[cid]["consumed"] = True
            return httpx.Response(200, json=record)
        return httpx.Response(404, json={"detail": "not found"})

    manager = _central_manager(handler)
    cid = await manager.request_confirmation(
        "launch_application", {"app_name": "calc"}, "YELLOW",
        reason="r", session_id="sess-1", call_id="call-1",
        remaining_calls=[{"tool_name": "echo", "arguments": {}, "call_id": "call-2"}],
    )
    assert cid.startswith("confirm-")
    assert seen["create"]["remaining_calls"] == [
        {"tool_name": "echo", "arguments": {}, "call_id": "call-2"}]
    assert manager.approve(cid) is True
    result = manager.consume(cid, session_id="sess-1")
    assert result is not None and result["approved"] is True
    assert result["remaining_calls"] == [
        {"tool_name": "echo", "arguments": {}, "call_id": "call-2"}]
    # RAM was never used: second consume hits the server again (409 -> None)
    assert manager.consume(cid, session_id="sess-1") is None


@pytest.mark.asyncio
async def test_manager_central_survives_core_restart():
    """A pending confirmation outlives the manager process (fresh manager, same SERVER)."""
    store = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        if request.method == "POST" and request.url.path == "/api/confirmations/":
            body = _json.loads(request.content.decode())
            store[body["confirmation_id"]] = body
            return httpx.Response(200, json={"confirmation_id": body["confirmation_id"], "created": True})
        if request.method == "POST" and request.url.path.endswith("/resolve"):
            cid = request.url.path.split("/")[3]
            store[cid]["approved"] = True
            store[cid]["resolved_at"] = 1.0
            return httpx.Response(200, json={"confirmation_id": cid, "approved": True})
        if request.method == "POST" and request.url.path.endswith("/consume"):
            cid = request.url.path.split("/")[3]
            if store[cid].get("consumed"):
                return httpx.Response(409, json={"detail": "consumed"})
            store[cid]["consumed"] = True
            record = dict(store[cid])
            return httpx.Response(200, json=record)
        return httpx.Response(404, json={"detail": "not found"})

    manager1 = _central_manager(handler)
    cid = await manager1.request_confirmation("echo", {"message": "hi"}, "GREEN", session_id="sess-r")
    assert manager1.approve(cid) is True
    del manager1  # simulate CORE restart: RAM state gone

    manager2 = _central_manager(handler)
    result = manager2.consume(cid, session_id="sess-r")
    assert result is not None and result["approved"] is True
    assert result["tool_name"] == "echo"
    assert manager2.consume(cid, session_id="sess-r") is None  # still single-use


@pytest.mark.asyncio
async def test_manager_central_denial_and_session_binding():
    seen_resolve = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        if request.url.path.endswith("/resolve"):
            seen_resolve.update(_json.loads(request.content.decode()))
            return httpx.Response(200, json={"confirmation_id": "cid-d", "approved": False})
        if request.url.path.endswith("/consume"):
            body = _json.loads(request.content.decode())
            if body.get("session_id") != "sess-ok":
                return httpx.Response(409, json={"detail": "session mismatch"})
            return httpx.Response(200, json={
                "confirmation_id": "cid-d", "tool_name": "t", "arguments": {},
                "security_level": "YELLOW", "reason": "", "session_id": "sess-ok",
                "call_id": "", "remaining_calls": [], "approved": False,
                "resolved_at": 1.0, "consumed": 1,
            })
        return httpx.Response(404, json={"detail": "not found"})

    manager = _central_manager(handler)
    assert manager.deny("cid-d") is True
    assert seen_resolve == {"approved": False}
    assert manager.consume("cid-d", session_id="sess-wrong") is None
    result = manager.consume("cid-d", session_id="sess-ok")
    assert result is not None and result["approved"] is False


@pytest.mark.asyncio
async def test_manager_central_required_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setenv("JARVIS_CENTRAL_STATE_REQUIRED", "true")
    reset_settings()
    manager = _central_manager(handler)
    from core.network.central_state_client import CentralStateError
    with pytest.raises(CentralStateError):
        await manager.request_confirmation("echo", {}, "GREEN")
    with pytest.raises(CentralStateError):
        manager.consume("cid-x", session_id="sess-1")
