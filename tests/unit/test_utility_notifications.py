"""Unit tests for notification tools + service (Phase 15.1).

The shared service singleton is reset per test (fresh isolated DB via
conftest). No real providers exist: push/desktop stay pending honestly,
webhook delivery is exercised with MockTransport.
"""

import logging

import httpx
import pytest

import core.notifications.service as service_mod
from core.notifications.service import (
    NotificationService,
    NotificationStatus,
    get_notification_service,
)
from memory.sqlite_provider import SQLiteMemoryProvider
from tools.builtin.notification_tool import (
    CheckPendingNotificationsTool,
    SendNotificationTool,
)
from tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _fresh_service(tmp_path):
    service_mod._service = None
    yield
    service_mod._service = None


def _service(tmp_path):
    return NotificationService(memory=SQLiteMemoryProvider(db_path=str(tmp_path / "n.db")))


@pytest.mark.asyncio
async def test_create_notification_pending_and_listed(tmp_path):
    service = _service(tmp_path)
    created = await service.create(title="Hi", message="body text")
    assert created["notification_id"].startswith("notif-")
    assert created["status"] == NotificationStatus.PENDING
    assert created["priority"] == "normal"
    assert created["channel"] == "push"
    assert created["delivered_at"] is None

    pending = await service.list_pending()
    assert [n["notification_id"] for n in pending] == [created["notification_id"]]

    fetched = await service.get(created["notification_id"])
    assert fetched["title"] == "Hi"
    assert await service.get("notif-missing") is None


@pytest.mark.asyncio
async def test_invalid_channel_and_priority_rejected(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ValueError):
        await service.create(title="t", message="m", channel="sms")
    with pytest.raises(ValueError):
        await service.create(title="t", message="m", priority="urgent!!")


@pytest.mark.asyncio
async def test_webhook_unconfigured_fails_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_NOTIFICATION_WEBHOOK_URL", "")
    service = _service(tmp_path)
    created = await service.create(title="t", message="m", channel="webhook")
    assert created["status"] == NotificationStatus.FAILED
    assert "webhook" in (created["error"] or "").lower()
    assert await service.list_pending() == []


@pytest.mark.asyncio
async def test_webhook_delivered_and_failed_paths(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content.decode())
        assert set(body) == {"notification_id", "title", "message", "priority"}
        if body["title"] == "boom":
            return httpx.Response(500, json={"error": "x"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    monkeypatch.setenv("JARVIS_NOTIFICATION_WEBHOOK_URL", "https://hooks.test/jarvis")
    service = NotificationService(
        memory=SQLiteMemoryProvider(db_path=str(tmp_path / "n.db")),
        webhook_transport=transport,
    )
    ok_result = await service.create(title="ok", message="m", channel="webhook")
    assert ok_result["status"] == NotificationStatus.DELIVERED
    assert ok_result["delivered_at"] is not None

    bad_result = await service.create(title="boom", message="m", channel="webhook")
    assert bad_result["status"] == NotificationStatus.FAILED
    assert "500" in (bad_result["error"] or "")
    assert await service.list_pending() == []


@pytest.mark.asyncio
async def test_send_tool_and_pending_tool_roundtrip():
    registry = ToolRegistry()
    registry.register(SendNotificationTool())
    registry.register(CheckPendingNotificationsTool())

    sent = await registry.execute_tool(
        "send_notification",
        {"title": "Hello", "message": "push body", "priority": "high", "channel": "push"},
        source="orchestrator",
    )
    assert sent.success is True
    assert sent.data["status"] == NotificationStatus.PENDING
    assert sent.data["priority"] == "high"

    listed = await registry.execute_tool("check_pending_notifications", {}, source="orchestrator")
    assert listed.success is True
    assert listed.data["count"] == 1
    assert listed.data["pending"][0]["title"] == "Hello"
    # Listing must not deliver
    again = await registry.execute_tool("check_pending_notifications", {}, source="orchestrator")
    assert again.data["count"] == 1


@pytest.mark.asyncio
async def test_send_tool_rejects_bad_enums():
    registry = ToolRegistry()
    registry.register(SendNotificationTool())
    bad = await registry.execute_tool(
        "send_notification", {"title": "t", "message": "m", "channel": "carrier-pigeon"},
        source="orchestrator",
    )
    assert bad.success is False


@pytest.mark.asyncio
async def test_no_secrets_in_logs(tmp_path, caplog):
    svc = NotificationService(
        memory=SQLiteMemoryProvider(db_path=str(tmp_path / "n.db")))
    with caplog.at_level(logging.INFO, logger="jarvis.notifications"):
        created = await svc.create(title="tok", message="secret-body-xyz", channel="push")
    assert "secret-body-xyz" not in caplog.text
    assert created["message"] == "secret-body-xyz"  # stored, just never logged
