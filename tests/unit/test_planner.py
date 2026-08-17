"""Unit tests for Planner and Execution Engine."""

import pytest
from core.contracts.enums import SecurityLevel, TaskStatus
from core.planner.builder import PlanBuilder
from core.planner.engine import PlanExecutor
from memory.sqlite_provider import SQLiteMemoryProvider
from tools.registry import ToolRegistry
from tools import register_default_tools


@pytest.fixture
def populated_registry():
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry


@pytest.fixture
async def memory_provider(tmp_path):
    db_file = str(tmp_path / "planner_test.db")
    provider = SQLiteMemoryProvider(db_path=db_file)
    await provider.initialize()
    yield provider
    await provider.close()


@pytest.mark.asyncio
async def test_planner_all_green_steps(populated_registry, memory_provider):
    builder = PlanBuilder(goal="Check system status and echo confirmation")
    builder.add_step(
        step_id="step-1",
        tool_name="get_system_metrics",
        description="Fetch CPU and RAM",
        security_level=SecurityLevel.GREEN,
    )
    builder.add_step(
        step_id="step-2",
        tool_name="echo",
        parameters={"message": "System status OK"},
        description="Echo confirmation",
        security_level=SecurityLevel.GREEN,
        depends_on=["step-1"],
    )
    plan = builder.build()

    executor = PlanExecutor(tool_registry=populated_registry, memory_provider=memory_provider)
    result = await executor.execute_plan(plan)

    assert result.status == TaskStatus.COMPLETED
    assert result.steps_executed == 2
    assert result.error is None
    assert result.step_results["step-1"].success is True
    assert result.step_results["step-2"].data == {"echo": "System status OK"}

    # Verify audit logs in SQLite
    audits = await memory_provider.get_recent_audits()
    assert len(audits) >= 2


@pytest.mark.asyncio
async def test_planner_yellow_step_pauses_for_approval(populated_registry, memory_provider):
    builder = PlanBuilder(goal="Open notepad application")
    builder.add_step(
        step_id="step-launch",
        tool_name="launch_application",
        parameters={"app_name": "notepad"},
        security_level=SecurityLevel.YELLOW,
    )
    plan = builder.build()

    executor = PlanExecutor(tool_registry=populated_registry, memory_provider=memory_provider)
    
    # Without confirmation
    result_unconfirmed = await executor.execute_plan(plan, confirmed_steps={})
    assert result_unconfirmed.status == TaskStatus.REQUIRE_APPROVAL
    assert "requires explicit user confirmation" in result_unconfirmed.error

    # With confirmation
    result_confirmed = await executor.execute_plan(plan, confirmed_steps={"step-launch": True})
    assert result_confirmed.status == TaskStatus.COMPLETED
    assert result_confirmed.step_results["step-launch"].success is True


@pytest.mark.asyncio
async def test_planner_fails_on_broken_dependency(populated_registry):
    builder = PlanBuilder(goal="Dependent tasks with failing root")
    builder.add_step(
        step_id="failing-step",
        tool_name="launch_application",
        parameters={"app_name": "unknown_app"},
        security_level=SecurityLevel.YELLOW,
    )
    builder.add_step(
        step_id="subsequent-step",
        tool_name="echo",
        parameters={"message": "This should not run"},
        depends_on=["failing-step"],
    )
    plan = builder.build()

    executor = PlanExecutor(tool_registry=populated_registry)
    result = await executor.execute_plan(plan, confirmed_steps={"failing-step": True})

    assert result.status == TaskStatus.FAILED
    assert result.steps_executed == 1
    assert "subsequent-step" not in result.step_results
