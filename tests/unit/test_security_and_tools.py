"""Unit tests for Tool System and Security Engine."""

import pytest
from core.contracts.enums import SecurityLevel
from security.allowlist import AllowlistValidator, SecurityValidationError
from security.policy_engine import PolicyEngine, PolicyDecision
from security.auth import verify_api_key
from tools.registry import ToolRegistry
from tools.builtin.echo_tool import EchoTool
from tools.builtin.telemetry_tool import GetSystemMetricsTool
from tools.builtin.process_tool import ListProcessesTool
from tools.builtin.app_tool import LaunchApplicationTool
from tools import register_default_tools


def test_allowlist_validator_apps():
    validator = AllowlistValidator(allowed_apps={"notepad": "notepad.exe", "calc": "calc.exe"})
    
    # Valid alias
    assert validator.get_allowed_executable("notepad") == "notepad.exe"
    assert validator.get_allowed_executable("calc") == "calc.exe"
    assert validator.get_allowed_executable("NOTEPAD.EXE") == "notepad.exe"

    # Forbidden app
    with pytest.raises(SecurityValidationError, match="not in the approved allowlist"):
        validator.get_allowed_executable("powershell.exe -enc malicious")

    with pytest.raises(SecurityValidationError, match="not in the approved allowlist"):
        validator.get_allowed_executable("cmd.exe")


def test_allowlist_validator_injection_prevention():
    validator = AllowlistValidator()
    with pytest.raises(SecurityValidationError, match="forbidden characters"):
        validator.sanitize_input_string("notepad & echo pwned")

    with pytest.raises(SecurityValidationError, match="forbidden characters"):
        validator.sanitize_input_string("calc; rm -rf /")

    with pytest.raises(SecurityValidationError, match="forbidden characters"):
        validator.sanitize_input_string("app | nc 1.2.3.4")


def test_policy_engine_green_yellow_red():
    policy = PolicyEngine()
    echo_tool = EchoTool()
    launch_tool = LaunchApplicationTool()

    # GREEN is automatically allowed
    green_decision = policy.evaluate(echo_tool.metadata, {"message": "hello"}, confirmed=False)
    assert green_decision.allowed is True

    # YELLOW without confirmation is blocked
    yellow_unconfirmed = policy.evaluate(launch_tool.metadata, {"app_name": "notepad"}, confirmed=False)
    assert yellow_unconfirmed.allowed is False
    assert yellow_unconfirmed.requires_confirmation is True

    # YELLOW with confirmation is allowed
    yellow_confirmed = policy.evaluate(launch_tool.metadata, {"app_name": "notepad"}, confirmed=True)
    assert yellow_confirmed.allowed is True


def test_policy_engine_injection_blocking():
    policy = PolicyEngine()
    echo_tool = EchoTool()

    decision = policy.evaluate(echo_tool.metadata, {"message": "hello; reboot"}, confirmed=True)
    assert decision.allowed is False
    assert "sanitization" in decision.reason


@pytest.mark.asyncio
async def test_tool_registry_and_execution():
    registry = ToolRegistry()
    register_default_tools(registry)

    assert registry.get("echo") is not None
    assert registry.get("get_system_metrics") is not None
    assert registry.get("list_processes") is not None
    assert registry.get("launch_application") is not None

    # Test Echo
    echo_res = await registry.execute_tool("echo", {"message": "JARVIS online"}, confirmed=False)
    assert echo_res.success is True
    assert echo_res.data == {"echo": "JARVIS online"}

    # Test Telemetry (Real system data)
    telem_res = await registry.execute_tool("get_system_metrics", {}, confirmed=False)
    assert telem_res.success is True
    assert "cpu" in telem_res.data
    assert "memory" in telem_res.data
    assert telem_res.data["cpu"]["cores_logical"] >= 1
    assert telem_res.data["memory"]["total_bytes"] > 0

    # Test List Processes
    proc_res = await registry.execute_tool("list_processes", {"limit": 5}, confirmed=False)
    assert proc_res.success is True
    assert len(proc_res.data["processes"]) <= 5
    assert proc_res.data["total_running"] > 0

    # Test Unregistered tool
    missing_res = await registry.execute_tool("non_existent_tool", {})
    assert missing_res.success is False
    assert "not registered" in missing_res.error


@pytest.mark.asyncio
async def test_tool_execution_yellow_security_policy():
    registry = ToolRegistry()
    register_default_tools(registry)

    # Launch without confirmation must fail
    res_no_confirm = await registry.execute_tool("launch_application", {"app_name": "notepad"}, confirmed=False)
    assert res_no_confirm.success is False
    assert "Policy Denied" in res_no_confirm.error
    assert "requires user confirmation" in res_no_confirm.error

    # Launch unauthorized app with confirmation must fail at allowlist check
    res_unauth = await registry.execute_tool("launch_application", {"app_name": "malicious_app"}, confirmed=True)
    assert res_unauth.success is False
    assert "not in the approved allowlist" in res_unauth.error
