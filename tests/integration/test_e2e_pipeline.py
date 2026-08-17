"""End-to-End Integration tests for full JARVIS execution pipeline."""

import pytest
from httpx import AsyncClient, ASGITransport
from server.app import create_app
from core.config import get_settings
from memory.sqlite_provider import SQLiteMemoryProvider
from core.planner.builder import PlanBuilder
from core.planner.engine import PlanExecutor
from tools.registry import get_tool_registry


@pytest.fixture
async def integrated_environment(tmp_path):
    """Setup an integrated test environment with temporary database and app instance."""
    db_file = str(tmp_path / "e2e_jarvis.db")
    memory = SQLiteMemoryProvider(db_path=db_file)
    await memory.initialize()
    
    app = create_app()
    registry = get_tool_registry()
    settings = get_settings()
    auth_headers = {"Authorization": f"Bearer {settings.api_key}"}

    yield {
        "app": app,
        "memory": memory,
        "registry": registry,
        "headers": auth_headers,
    }
    await memory.close()


@pytest.mark.asyncio
async def test_e2e_api_to_execution_flow(integrated_environment):
    app = integrated_environment["app"]
    headers = integrated_environment["headers"]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Health & Telemetry check
        health_resp = await client.get("/health", headers=headers)
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "healthy"
        assert health_data["registered_tools_count"] >= 5

        # Step 2: Query Telemetry
        telem_resp = await client.get("/telemetry", headers=headers)
        assert telem_resp.status_code == 200
        assert telem_resp.json()["cpu"]["cores_logical"] >= 1

        # Step 3: Execute green tool via API
        exec_resp = await client.post(
            "/tools/execute",
            json={"tool_name": "get_system_metrics", "parameters": {}, "confirmed": False},
            headers=headers,
        )
        assert exec_resp.status_code == 200
        assert exec_resp.json()["success"] is True

        # Step 4: Execute yellow tool with rejection when unconfirmed
        yellow_unconfirmed = await client.post(
            "/tools/execute",
            json={"tool_name": "launch_application", "parameters": {"app_name": "notepad"}, "confirmed": False},
            headers=headers,
        )
        assert yellow_unconfirmed.status_code == 200
        assert yellow_unconfirmed.json()["success"] is False
        assert "requires user confirmation" in yellow_unconfirmed.json()["error"]


@pytest.mark.asyncio
async def test_e2e_planner_to_memory_audit_trail(integrated_environment):
    registry = integrated_environment["registry"]
    memory = integrated_environment["memory"]

    # Plan with 2 steps
    builder = PlanBuilder(goal="E2E Diagnostic & Reporting Workflow")
    builder.add_step("diag-1", "get_system_metrics", description="Collect system health")
    builder.add_step("diag-2", "echo", parameters={"message": "All systems operational"}, depends_on=["diag-1"])

    plan = builder.build()
    executor = PlanExecutor(tool_registry=registry, memory_provider=memory)

    result = await executor.execute_plan(plan)
    assert result.status.value == "COMPLETED"
    assert result.steps_executed == 2

    # Check that audit log entries were persisted in SQLite
    audits = await memory.get_recent_audits(limit=10)
    assert len(audits) >= 2
    tool_names = [a.tool_name for a in audits]
    assert "echo" in tool_names
    assert "get_system_metrics" in tool_names
