"""Unit tests for SQLite Memory Provider."""

import os
import pytest
from datetime import datetime, timezone
from memory.sqlite_provider import SQLiteMemoryProvider
from core.contracts.memory import AuditEntry
from core.contracts.enums import SecurityLevel


@pytest.fixture
async def memory_provider(tmp_path):
    db_file = str(tmp_path / "test_jarvis.db")
    provider = SQLiteMemoryProvider(db_path=db_file)
    await provider.initialize()
    yield provider
    await provider.close()


@pytest.mark.asyncio
async def test_memory_key_value_crud(memory_provider):
    # Set
    await memory_provider.set("user_theme", "dark", category="preferences")
    await memory_provider.set("active_workspace", {"name": "Eryndor", "path": "C:/Projects/Eryndor"}, category="workspace")

    # Get
    theme_entry = await memory_provider.get("user_theme")
    assert theme_entry is not None
    assert theme_entry.value == "dark"
    assert theme_entry.category == "preferences"

    workspace_entry = await memory_provider.get("active_workspace")
    assert workspace_entry is not None
    assert workspace_entry.value["name"] == "Eryndor"

    # Non existent
    missing = await memory_provider.get("unknown_key")
    assert missing is None

    # Update
    await memory_provider.set("user_theme", "cyberpunk", category="preferences")
    updated_theme = await memory_provider.get("user_theme")
    assert updated_theme.value == "cyberpunk"

    # Delete
    deleted = await memory_provider.delete("user_theme")
    assert deleted is True
    assert await memory_provider.get("user_theme") is None


@pytest.mark.asyncio
async def test_memory_list_by_category(memory_provider):
    await memory_provider.set("cfg.a", 1, category="network")
    await memory_provider.set("cfg.b", 2, category="network")
    await memory_provider.set("cfg.c", 3, category="other")

    network_entries = await memory_provider.list_by_category("network")
    assert len(network_entries) == 2
    keys = [e.key for e in network_entries]
    assert "cfg.a" in keys
    assert "cfg.b" in keys


@pytest.mark.asyncio
async def test_memory_audit_logging(memory_provider):
    entry1 = AuditEntry(
        node_id="node2-dev",
        tool_name="get_system_metrics",
        security_level=SecurityLevel.GREEN,
        parameters={},
        success=True,
        duration_ms=10.5,
    )
    entry2 = AuditEntry(
        node_id="node2-dev",
        tool_name="launch_application",
        security_level=SecurityLevel.YELLOW,
        parameters={"app_name": "notepad"},
        success=True,
        duration_ms=45.2,
    )

    await memory_provider.log_audit(entry1)
    await memory_provider.log_audit(entry2)

    audits = await memory_provider.get_recent_audits(limit=10)
    assert len(audits) == 2
    # Check most recent first
    assert audits[0].tool_name == "launch_application"
    assert audits[0].security_level == SecurityLevel.YELLOW
    assert audits[1].tool_name == "get_system_metrics"
    assert audits[1].security_level == SecurityLevel.GREEN
