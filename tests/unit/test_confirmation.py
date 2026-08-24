"""Tests for the confirmation flow: approve→resume, deny→cancel, invalid/expired cid, double-use."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.orchestrator.confirmation import ConfirmationManager


class TestConfirmationManagerUnit:
    """Unit tests for ConfirmationManager."""

    @pytest.mark.asyncio
    async def test_request_and_approve_and_consume(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="launch_application",
            arguments={"app_name": "notepad"},
            security_level="YELLOW",
            reason="Needs approval",
            session_id="sess-123",
            call_id="call-001",
        )
        assert cid is not None

        approved = manager.approve(cid)
        assert approved is True

        result = manager.consume(cid, session_id="sess-123")
        assert result is not None
        assert result["approved"] is True
        assert result["tool_name"] == "launch_application"
        assert result["arguments"] == {"app_name": "notepad"}
        assert result["call_id"] == "call-001"

    @pytest.mark.asyncio
    async def test_deny_and_consume(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="launch_application",
            arguments={"app_name": "notepad"},
            security_level="YELLOW",
            session_id="sess-456",
        )
        manager.deny(cid)

        result = manager.consume(cid, session_id="sess-456")
        assert result is not None
        assert result["approved"] is False

    @pytest.mark.asyncio
    async def test_consume_single_use(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="echo", arguments={}, security_level="GREEN",
            session_id="sess-789",
        )
        manager.approve(cid)

        # First consume succeeds
        result1 = manager.consume(cid, session_id="sess-789")
        assert result1 is not None
        assert result1["approved"] is True

        # Second consume fails (single-use)
        result2 = manager.consume(cid, session_id="sess-789")
        assert result2 is None

    @pytest.mark.asyncio
    async def test_consume_session_mismatch(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="echo", arguments={}, security_level="GREEN",
            session_id="sess-A",
        )
        manager.approve(cid)

        # Different session
        result = manager.consume(cid, session_id="sess-B")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_not_found(self):
        manager = ConfirmationManager()
        result = manager.consume("confirm-nonexistent", session_id="sess-X")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_not_yet_resolved(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="echo", arguments={}, security_level="GREEN",
            session_id="sess-000",
        )
        # Not approved or denied yet
        result = manager.consume(cid, session_id="sess-000")
        assert result is None

    @pytest.mark.asyncio
    async def test_wait_for_confirmation_approved(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid = await manager.request_confirmation(
            tool_name="echo", arguments={}, security_level="GREEN",
        )
        manager.approve(cid)
        result = await manager.wait_for_confirmation(cid, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_confirmation_timeout(self):
        manager = ConfirmationManager(default_timeout=0.1)
        cid = await manager.request_confirmation(
            tool_name="echo", arguments={}, security_level="GREEN",
        )
        result = await manager.wait_for_confirmation(cid, timeout=0.15)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_pending(self):
        manager = ConfirmationManager(default_timeout=5.0)
        cid1 = await manager.request_confirmation(
            tool_name="tool_a", arguments={}, security_level="YELLOW",
            session_id="s1",
        )
        cid2 = await manager.request_confirmation(
            tool_name="tool_b", arguments={}, security_level="RED",
            session_id="s1",
        )
        pending = manager.list_pending()
        assert len(pending) == 2
        ids = {p["confirmation_id"] for p in pending}
        assert cid1 in ids
        assert cid2 in ids

        manager.approve(cid1)
        pending_after = manager.list_pending()
        assert len(pending_after) == 1
        assert pending_after[0]["confirmation_id"] == cid2
