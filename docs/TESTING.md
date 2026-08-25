# J.A.R.V.I.S. — Test Suite

## Overview

JARVIS uses **pytest** with **pytest-asyncio** for automated testing. The test suite covers unit tests and integration tests across all major components.

**Current status:** 230 tests passing, 0 failures, 0 warnings.

## Running Tests

```bash
# Full test suite (verbose)
pytest -v

# Quiet mode (summary only)
pytest -q --no-header -p no:cacheprovider

# Run a specific test file
pytest tests/unit/test_goal_engine.py -v

# Run a specific test
pytest tests/unit/test_agent_system.py::test_agent_creation -v
```

## Test Structure

```
tests/
  conftest.py                        # Shared fixtures, DB isolation, singleton resets
  unit/
    test_config_and_contracts.py     # Pydantic contracts and config validation
    test_planner.py                  # PlanBuilder and PlanExecutor
    test_memory_sqlite.py            # SQLiteMemoryProvider operations
    test_security_and_tools.py       # PolicyEngine, ToolRegistry, built-in tools
    test_windows_agent.py            # WindowsSystemCollector telemetry
    test_api_server.py               # FastAPI endpoints (health, tools)
    test_confirmation.py             # ConfirmationManager (approve, deny, single-use)
    test_mcp_policy.py               # MCP protocol security (GREEN/YELLOW/RED)
    test_external_provider.py        # ExternalProvider (OpenAI-compatible)
    test_provider_registry.py        # ProviderRegistry registration and health
    test_intelligence_router.py      # IntelligenceRouter fallback and circuit breaker
    test_provider_visibility.py      # Tool visibility (LOCAL_ONLY vs SHARED)
    test_net_guard.py                # Anti-SSRF protection
    test_file_sandbox.py             # File tool sandboxing
    test_new_components.py           # EventBus, ContextBuilder, ConversationManager
    test_agent_system.py             # Agent, AgentFactory, AgentSecurityValidator
    test_goal_engine.py              # GoalEngine lifecycle and replanning
  integration/
    test_ai_pipeline.py              # End-to-end LLM → tool execution pipeline
    test_e2e_pipeline.py             # Full conversation flow
    test_multi_provider_flow.py      # Multi-provider fallback integration
    test_goal_agent_integration.py   # Goal Engine + Agent System integration
```

## Test Isolation

Every test runs in complete isolation:

1. **Database isolation**: Each test gets a temporary SQLite database via `tmp_path`. The production `data/jarvis.db` is never touched.
2. **Singleton resets**: All global singletons (ToolRegistry, ProviderRegistry, EventBus, ConfirmationManager) are reset between tests.
3. **Garbage collection**: `gc.collect()` is forced after each test to prevent aiosqlite thread hangs.

## Test Database Hash

The production database hash is tracked to verify tests never modify it:
```
D8A125F20EB72BEBE45D0378CECED2A2
```

## Adding New Tests

When adding a new test file:
1. Place unit tests in `tests/unit/`
2. Place integration tests in `tests/integration/`
3. Use the existing fixtures from `conftest.py` (they auto-apply)
4. Follow the naming convention `test_*.py`
5. Run the full suite to ensure no regressions
