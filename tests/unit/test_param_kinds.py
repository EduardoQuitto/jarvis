"""Regression tests for ParamKind-based parameter validation (Bug 1).

Shell protection moved from "every string everywhere" to the correct
boundary: only SHELL_ARG (default) and IDENT params are shell-checked.
FREE_TEXT/PATH/URL params accept realistic content.
"""

import pytest

from core.contracts.enums import ParamKind
from security.policy_engine import PolicyEngine
from tools.registry import ToolRegistry
from tools import register_default_tools


@pytest.fixture
def registry():
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def _eval(registry, tool_name, params, source="operator"):
    policy = PolicyEngine()
    return policy.evaluate(registry.get(tool_name).metadata, params, confirmed=True, source=source)


REALISTIC_TEXT = "Linha 1: custo R$ 89,90 (promo&frete)\nLinha 2: ver https://ex.com/?a=1&b=2 (ok)"


def test_free_text_allows_realistic_content(registry):
    for tool_name, params in [
        ("echo", {"message": REALISTIC_TEXT}),
        ("web_search", {"query": REALISTIC_TEXT}),
        ("write_file", {"file_path": "notes.txt", "content": REALISTIC_TEXT}),
        ("create_task", {"objective": REALISTIC_TEXT, "context": '{"a": [1, 2]}'}),
        ("search_memory", {"query": "user (Sergio) & prefs $x"}),
    ]:
        decision = _eval(registry, tool_name, params)
        assert decision.allowed is True, f"{tool_name} rejected realistic content: {decision.reason}"


def test_url_allows_querystrings_but_rejects_non_http(registry):
    ok = _eval(registry, "fetch_url", {"url": "https://ex.com/search?q=a&b=2"})
    assert ok.allowed is True
    bad = _eval(registry, "fetch_url", {"url": "ftp://ex.com/x"})
    assert bad.allowed is False
    bad2 = _eval(registry, "fetch_url", {"url": "not a url"})
    assert bad2.allowed is False


def test_path_blocks_traversal_but_allows_parens(registry):
    # Containment is enforced against settings.allowed_paths, which include
    # the working directory by default.
    import os
    allowed = os.path.abspath(".")
    inside = os.path.join(allowed, "Program Files (x86)", "app.txt")
    ok = _eval(registry, "read_file", {"file_path": inside})
    assert ok.allowed is True, ok.reason

    outside = _eval(registry, "read_file", {"file_path": "/etc/passwd"})
    assert outside.allowed is False


def test_ident_allows_aliases_but_blocks_injection(registry):
    ok = _eval(registry, "launch_application", {"app_name": "notepad"})
    assert ok.allowed is True
    for evil in ["notepad; reboot", "calc & echo pwned", "app | nc 1.2.3.4", "x$(y)", "a`b`"]:
        denied = _eval(registry, "launch_application", {"app_name": evil})
        assert denied.allowed is False, f"IDENT accepted {evil!r}"


def test_undeclared_string_params_stay_strict():
    # A tool that declares nothing keeps the old strict behavior: protection
    # is never silently dropped.
    from tools.base import FunctionalTool

    async def _noop(**kwargs):
        return {"ok": True}

    tool = FunctionalTool(name="undeclared_probe", description="probe", func=_noop)
    policy = PolicyEngine()
    denied = policy.evaluate(tool.metadata, {"arg": "a; reboot"}, confirmed=True, source="operator")
    assert denied.allowed is False
    allowed = policy.evaluate(tool.metadata, {"arg": "plain text"}, confirmed=True, source="operator")
    assert allowed.allowed is True


def test_param_kind_enum_values():
    assert {k.value for k in ParamKind} == {"FREE_TEXT", "PATH", "URL", "SHELL_ARG", "IDENT"}


def test_metadata_carries_param_kinds(registry):
    meta = registry.get("echo").metadata
    assert meta.param_kinds == {"message": "FREE_TEXT"}
    meta2 = registry.get("launch_application").metadata
    assert meta2.param_kinds == {"app_name": "IDENT"}
