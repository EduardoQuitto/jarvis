"""Shared test fixtures and cleanup for JARVIS test suite."""

import gc
import os
import warnings

import pytest

from core.config import reset_settings


@pytest.fixture(autouse=True)
def _isolate_test_environment(tmp_path, monkeypatch):
    """Isolate every test in a clean environment.

    - DB path is a per-test temp file (never touches data/jarvis.db).
    - All global singletons are reset between tests.
    - gc.collect() is forced so aiosqlite's non-daemon worker thread
      closes via __del__ instead of hanging pytest at exit.
    """
    # 1. Isolate DB
    test_db = str(tmp_path / "test.db")
    monkeypatch.setenv("JARVIS_DB_PATH", test_db)
    reset_settings()

    # 2. Reset tool registry
    from tools.registry import get_tool_registry, ToolRegistry
    import tools.registry as _tr_mod
    _tr_mod._registry = None

    # 3. Reset provider registry
    from core.llm.registry import get_provider_registry, ProviderRegistry
    import core.llm.registry as _pr_mod
    _pr_mod._provider_registry = None

    # 4. Reset event bus
    from core.events.bus import get_event_bus
    import core.events.bus as _eb_mod
    _eb_mod._event_bus = None

    # 5. Reset confirmation manager
    from core.orchestrator.confirmation import get_confirmation_manager
    import core.orchestrator.confirmation as _cm_mod
    _cm_mod._confirmation_manager = None

    # 6. Reset chat module orchestrator (avoids retaining globals across tests)
    try:
        import server.routers.chat as _chat_mod
        _chat_mod._orchestrator = None
    except (ImportError, AttributeError):
        pass

    # 7. Reset tasks/devices routers globals
    try:
        import server.routers.tasks as _tasks_mod
        _tasks_mod._task_manager = None
    except (ImportError, AttributeError):
        pass
    try:
        import server.routers.devices as _devices_mod
        _devices_mod._registry = None
    except (ImportError, AttributeError):
        pass
    try:
        import server.routers.memory as _mem_mod
        _mem_mod._memory = None
    except (ImportError, AttributeError):
        pass

    yield

    # 8. Force GC to trigger aiosqlite __del__ on any lingering connections
    gc.collect()


@pytest.fixture(autouse=True)
def _suppress_aiosqlite_thread_warnings():
    """Suppress aiosqlite background thread warnings during test teardown."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        yield
