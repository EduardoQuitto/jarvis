"""Unit tests for Core Settings and Contracts."""

import pytest
from core.config import Settings, get_settings, reset_settings
from core.contracts.enums import NodeRole, SecurityLevel, TaskStatus
from core.contracts.telemetry import CPUMetrics, MemoryMetrics, DiskMetrics, SystemMetrics
from core.contracts.tool import ToolResult, ToolMetadata
from core.contracts.planner import TaskStep, ExecutionPlan
from core.contracts.memory import MemoryEntry, AuditEntry


def test_settings_default_values():
    reset_settings()
    settings = get_settings()
    assert settings.node_id == "node2-dev"
    assert settings.node_role == NodeRole.NODE2
    assert settings.allowlist_enabled is True
    assert "notepad" in settings.allowed_apps
    assert settings.is_production is False


def test_tool_result_constructors():
    ok_res = ToolResult.ok(data={"status": "active"}, security_level=SecurityLevel.GREEN, execution_time_ms=12.5)
    assert ok_res.success is True
    assert ok_res.data == {"status": "active"}
    assert ok_res.error is None
    assert ok_res.security_level == SecurityLevel.GREEN
    assert ok_res.execution_time_ms == 12.5

    fail_res = ToolResult.fail(error="Denied", security_level=SecurityLevel.RED, execution_time_ms=1.0)
    assert fail_res.success is False
    assert fail_res.data is None
    assert fail_res.error == "Denied"
    assert fail_res.security_level == SecurityLevel.RED


def test_telemetry_models_validation():
    cpu = CPUMetrics(usage_percent=15.2, cores_logical=4, cores_physical=2)
    mem = MemoryMetrics(total_bytes=8589934592, available_bytes=4294967296, used_bytes=4294967296, usage_percent=50.0)
    disk = DiskMetrics(mount_point="C:\\", total_bytes=500000000000, free_bytes=250000000000, used_bytes=250000000000, usage_percent=50.0)
    
    sys_metrics = SystemMetrics(
        node_id="node2-dev",
        os_name="Windows",
        os_version="10.0.19045",
        uptime_seconds=3600.0,
        cpu=cpu,
        memory=mem,
        disks=[disk],
    )
    assert sys_metrics.node_id == "node2-dev"
    assert sys_metrics.cpu.usage_percent == 15.2
    assert len(sys_metrics.disks) == 1


def test_planner_models_lifecycle():
    step1 = TaskStep(
        step_id="step-1",
        description="Check CPU usage",
        tool_name="get_system_metrics",
        security_level=SecurityLevel.GREEN,
    )
    assert step1.status == TaskStatus.PENDING

    plan = ExecutionPlan(
        plan_id="plan-101",
        goal="Diagnose system load",
        steps=[step1],
    )
    assert plan.status == TaskStatus.PENDING
    assert len(plan.steps) == 1
    assert plan.current_step_index == 0


def test_memory_and_audit_models():
    mem = MemoryEntry(key="user_name", value="Sergio", category="preference")
    assert mem.key == "user_name"
    assert mem.value == "Sergio"

    audit = AuditEntry(
        node_id="node2-dev",
        tool_name="launch_application",
        security_level=SecurityLevel.YELLOW,
        parameters={"app_name": "notepad"},
        success=True,
    )
    assert audit.security_level == SecurityLevel.YELLOW
    assert audit.tool_name == "launch_application"
