"""Unit tests for calculate_math + registry integration of all 13 tools (Phase 15.1)."""

import math

import pytest

from core.contracts.enums import ParamKind, SecurityLevel
from tools.registry import ToolRegistry
from tools import register_default_tools
from tools.builtin.utility_tool import CalculateMathTool


def _registry():
    registry = ToolRegistry()
    registry.register(CalculateMathTool())
    return registry


# --- calculate_math: allowed operations ---

@pytest.mark.asyncio
@pytest.mark.parametrize("expression,expected", [
    ("2 + 3 * 4", 14),
    ("(2 + 3) * 4", 20),
    ("10 / 4", 2.5),
    ("10 // 3", 3),
    ("10 % 3", 1),
    ("2 ** 10", 1024),
    ("-5 + 3", -2),
    ("abs(-7)", 7),
    ("round(2.5)", 2),
    ("sqrt(16)", 4.0),
    ("floor(2.9)", 2),
    ("ceil(2.1)", 3),
    ("log10(1000)", 3.0),
    ("exp(0)", 1.0),
])
async def test_math_allowed_operations(expression, expected):
    registry = _registry()
    result = await registry.execute_tool(
        "calculate_math", {"expression": expression}, source="orchestrator",
    )
    assert result.success is True, result.error
    assert result.data["result"] == pytest.approx(expected)
    assert result.data["expression"] == expression
    assert result.data["type"] in ("int", "float")


@pytest.mark.asyncio
async def test_math_constants_pi_e():
    registry = _registry()
    result = await registry.execute_tool(
        "calculate_math", {"expression": "pi * 2"}, source="orchestrator",
    )
    assert result.success is True
    assert result.data["result"] == pytest.approx(math.pi * 2)
    euler = await registry.execute_tool(
        "calculate_math", {"expression": "e + 0"}, source="orchestrator",
    )
    assert euler.data["result"] == pytest.approx(math.e)


@pytest.mark.asyncio
async def test_math_trig_and_log():
    registry = _registry()
    for expression, expected in [("sin(0)", 0.0), ("cos(0)", 1.0), ("tan(0)", 0.0),
                                 ("log(e)", 1.0)]:
        result = await registry.execute_tool(
            "calculate_math", {"expression": expression}, source="orchestrator",
        )
        assert result.success is True, expression
        assert result.data["result"] == pytest.approx(expected)


# --- calculate_math: rejections ---

@pytest.mark.asyncio
async def test_math_division_by_zero():
    registry = _registry()
    result = await registry.execute_tool(
        "calculate_math", {"expression": "1 / 0"}, source="orchestrator",
    )
    assert result.success is False
    assert "zero" in (result.error or "").lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("expression", [
    "__import__('os')",
    "open('/etc/passwd').read()",
    "eval('1+1')",
    "os.system('x')",
    "x + 1",
    "[1, 2, 3]",
    "{'a': 1}",
    "lambda x: x",
    "().__class__",
    "sqrt",
    "round(1, 2, 3, 4, 5, 6, 7, 8, 9)",
])
async def test_math_forbidden_constructs(expression):
    registry = _registry()
    result = await registry.execute_tool(
        "calculate_math", {"expression": expression}, source="orchestrator",
    )
    assert result.success is False, f"should reject: {expression}"


@pytest.mark.asyncio
async def test_math_dos_guards():
    registry = _registry()
    huge_pow = await registry.execute_tool(
        "calculate_math", {"expression": "10**100000"}, source="orchestrator",
    )
    assert huge_pow.success is False

    giant = await registry.execute_tool(
        "calculate_math", {"expression": "9" * 600}, source="orchestrator",
    )
    assert giant.success is False

    # Parens alone add no AST depth; a long left-assoc chain does.
    nested = await registry.execute_tool(
        "calculate_math", {"expression": "1" + "+1" * 30},
        source="orchestrator",
    )
    assert nested.success is False


@pytest.mark.asyncio
async def test_math_empty_and_garbage():
    registry = _registry()
    for expression in ("", "   ", "2 +* 3", "hello world"):
        result = await registry.execute_tool(
            "calculate_math", {"expression": expression}, source="orchestrator",
        )
        assert result.success is False, repr(expression)


# --- registry integration: all 13 tools ---

EXPECTED_TOOLS = {
    "ping_host": SecurityLevel.GREEN,
    "dns_lookup": SecurityLevel.GREEN,
    "get_network_interfaces": SecurityLevel.GREEN,
    "send_notification": SecurityLevel.GREEN,
    "check_pending_notifications": SecurityLevel.GREEN,
    "find_duplicates": SecurityLevel.GREEN,
    "disk_usage_analysis": SecurityLevel.GREEN,
    "generate_password": SecurityLevel.GREEN,
    "hash_file": SecurityLevel.GREEN,
    "verify_checksum": SecurityLevel.GREEN,
    "calculate_math": SecurityLevel.GREEN,
    "get_system_info": SecurityLevel.GREEN,
    "get_system_uptime": SecurityLevel.GREEN,
}


def test_all_13_tools_registered_green():
    registry = ToolRegistry()
    register_default_tools(registry)
    for name, level in EXPECTED_TOOLS.items():
        tool = registry.get(name)
        assert tool is not None, f"{name} not registered"
        assert tool.security_level == level, name
        assert tool.metadata.security_level == level


def test_param_kinds_declared():
    registry = ToolRegistry()
    register_default_tools(registry)
    assert registry.get("ping_host").metadata.param_kinds["hostname"] == ParamKind.FREE_TEXT.value
    assert registry.get("dns_lookup").metadata.param_kinds["domain"] == ParamKind.FREE_TEXT.value
    assert registry.get("send_notification").metadata.param_kinds["channel"] == ParamKind.IDENT.value
    assert registry.get("find_duplicates").metadata.param_kinds["directory"] == ParamKind.PATH.value
    assert registry.get("disk_usage_analysis").metadata.param_kinds["path"] == ParamKind.PATH.value
    assert registry.get("hash_file").metadata.param_kinds["file_path"] == ParamKind.PATH.value
    assert registry.get("verify_checksum").metadata.param_kinds["expected_hash"] == ParamKind.IDENT.value
    assert registry.get("calculate_math").metadata.param_kinds["expression"] == ParamKind.FREE_TEXT.value


@pytest.mark.asyncio
async def test_green_tools_execute_freely_through_policy():
    registry = ToolRegistry()
    register_default_tools(registry)
    for name, params in [
        ("calculate_math", {"expression": "6*7"}),
        ("get_system_uptime", {}),
        ("generate_password", {"length": 12, "complexity": "low"}),
        ("dns_lookup", {"domain": "localhost"}),
    ]:
        result = await registry.execute_tool(name, params, confirmed=False, source="orchestrator")
        assert result.success is True, f"{name}: {result.error}"
    calc = await registry.execute_tool(
        "calculate_math", {"expression": "6*7"}, confirmed=False, source="orchestrator")
    assert calc.data["result"] == 42
