# Changelog

All notable changes to the J.A.R.V.I.S. project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 11 — real-time streaming (SSE):**
  - `Orchestrator.stream_message()` emitting `OrchestratorStreamEvent` (`START`, `THINKING`, `TEXT_DELTA`, `TOOL_CALL`, `TOOL_RESULT`, `WAITING_CONFIRMATION`, `ERROR`, `DONE`).
  - `POST /api/chat/stream` serving `text/event-stream` with the same auth, policy gates, persistence and confirmation flow as `/api/chat/send` (unchanged).
  - Tool calls stream buffered and merged by id (never partial); text flows delta-by-delta; client disconnect cancels cleanly with no orphan tasks.
- **CORE ↔ SERVER bridge (`core/network/`):**
  - `RemoteNodeClient` — async HTTP transport (health, devices, tools, `POST /tools/execute` with `confirmed=False`), all failures normalized to `RemoteNodeError`.
  - `remote_server_tool` — controlled Core proxy: only SERVER-advertised SHARED tools, `LOCAL_ONLY` always rejected, `ToolResult` standardized.
  - `NodePresenceManager` — auto-registration (`POST /api/devices/`) + heartbeat (`POST /api/devices/heartbeat`) every 30s via FastAPI lifespan; offline SERVER only logs a warning, Core keeps working locally.
  - `DistributedTaskClient` — remote task lifecycle (create/get/list/progress/complete/fail/cancel/pause/resume) against `/api/tasks/*`; SERVER SQLite stays the source of truth. No worker/scheduler/queue.
  - Manual smoke scripts (excluded from pytest): `check_remote_server.py`, `check_remote_tasks.py`.
- **Google AI Studio (Gemini) cloud fallback:**
  - `JARVIS_GOOGLE_API_KEY/MODEL/BASE_URL` settings; `create_llm_provider("google")` and router slot `google` (priority 7, `local=False`) reusing `ExternalProvider` — Ollama stays primary (10), mock stays last (1).
  - Manual checks (excluded from pytest): `check_google_provider.py`, `check_llm_fallback.py` (real fallback Ollama → Google validated).
- **ExternalProvider resilience:** limited retry with exponential backoff (3 attempts, ~1s/~2s via `asyncio.sleep`) for transient HTTP 408/429/500/502/503/504 in `generate()`; permanent 4xx never retry; `LLMResponse(error_msg=...)`
contract preserved; streaming failures propagate (no fake success chunks) so `route_stream()` falls back before any
content and re-raises after content was emitted instead of mixing providers.
- Tests: 103 new tests (333 total) covering bridge, presence, lifespan, task lifecycle, Google slot, retry/backoff, and the confirmation flow below.

### Changed
- `server/routers/tasks.py`: `PATCH .../tasks/{id}` with `error` now appends to the `errors` history (previously wrote a nonexistent `error` column → HTTP 500); create accepts optional `conversation_id`.
- `server/app.py`: FastAPI lifespan wired into `create_app()` (previously defined but unused).
- `tests/conftest.py`: pins node identity + disables bridge/Google slots by default so the suite never depends on the developer's real `.env`.
- `README.md`: status and test counts updated.

### Fixed
- **Confirmation flow:** approved YELLOW/RED tools were denied again on resume (`operator_direct` never propagated) and failures were masked as "Action completed.". Resume now propagates the consumed approval and reports failures honestly. Covered by `test_orchestrator_confirmation.py`.
- Symlink sandbox tests skip conditionally on Windows without privilege (WinError 1314) instead of failing.

### Security
- No new routes, no remote shell, no arbitrary execution; cloud providers only ever see SHARED tools; API keys never logged/printed/committed.

## [0.5.0] - 2026-08-25

### Added
- **Security & Execution Boundary Hardening (Phase 10):**
  - `source` parameter propagated through PolicyEngine → ToolRegistry → ToolExecutor.
  - `UNTRUSTED_SOURCES`, `YELLOW_CAPABLE_SOURCES`, `OPERATOR_SOURCES` constants.
  - MCP Hardening: `tools/list` returns only SHARED tools; `tools/call` blocks LOCAL_ONLY.
  - PlanExecutor/StepExecutor: `confirmed_steps` removed, `source` propagated.
  - `AgentToolExecutor` — per-call permission validation for agents.
  - NetGuard: cloud metadata IP ranges (`169.254.169.254`, `169.254.169.253`) blocked.
  - NetGuard: `metadata.google.internal` hostname blocked.
  - CORS: `JARVIS_CORS_ORIGINS` env var for configurable origins.
  - ConfirmationManager: timestamps, expiry cleanup, reuse blocking, stats.
  - 28 adversarial security tests covering MCP bypass, confirmed=True bypass, SSRF, path traversal, visibility, confirmation reuse, and more.

### Changed
- `PolicyEngine.evaluate()` requires `source` parameter (default: `"orchestrator"`).
- `ToolRegistry.execute_tool()` requires `source` parameter.
- `ToolExecutor.execute_tool_call()` requires `source` parameter.
- `PlanExecutor.execute_plan()` no longer accepts `confirmed_steps` parameter.
- Orchestrator never passes `confirmed=True` from LLM path.
- CORS middleware restricted: production same-origin only, dev defaults to `localhost:3000`.
- Version bumped to 0.5.0.

### Security
- Untrusted sources (MCP, planner, step_executor, agent) have `confirmed=True` silently ignored.
- RED actions require `source="operator"` only — orchestrator and all other sources cannot confirm RED.
- YELLOW actions from untrusted sources always require confirmation.
- LOCAL_ONLY tools blocked from MCP and agent sources.

## [0.4.0] - 2026-08-24

### Added
- **Goal Engine:**
  - `GoalEngine` — manages high-level objectives with lifecycle (create/start/complete/fail/cancel).
  - `Goal`, `GoalResult`, `GoalStatus` contracts (`core/contracts/goal.py`).
  - `ReplanDecision` — decides retry/skip/abort/ask_user when steps fail.
  - Integration with `TaskManager` for persistence and `EventBus` for events.
- **Agent System:**
  - `Agent` — specialized executor with identity, permissions, and isolated context.
  - `AgentSpec`, `AgentState`, `AgentResult`, `AgentPermission` contracts (`core/contracts/agent.py`).
  - `AgentRegistry` — tracks active and completed agents.
  - `AgentFactory` — creates agents dynamically with security validation.
  - `AgentSecurityValidator` — enforces permission constraints and prevents privilege escalation.
  - Predefined agent types: `ResearchAgent`, `DeveloperAgent`, `AnalystAgent`, `CriticAgent`.
  - Agents are task-scoped (temporary) and cannot grant themselves permissions.
- **Planner Evolution:**
  - `PlanExecutor` now supports `ReplanCallback` for step failure handling.
  - Replan actions: `RETRY_SAME`, `SKIP_STEP`, `ALTERNATIVE_STEP`, `ABORT`, `ASK_USER`.
  - Step-level retry with `max_retries`.
- **Orchestrator Goal Integration:**
  - `GoalOrchestrator` — routes complex requests to GoalEngine, simple requests to normal Orchestrator.
  - Complexity detection via heuristic (action verbs, message length, multi-step indicators).
- **New Enums:**
  - `GoalStatus`: pending, planning, running, waiting_confirmation, blocked, failed, replanning, completed, cancelled.
  - `AgentStatus`: pending, running, waiting_confirmation, completed, failed, cancelled.
  - `ReplanAction`: retry_same, skip_step, alternative_step, abort, ask_user.
- **New Events:**
  - `GOAL_CREATED`, `GOAL_STARTED`, `GOAL_COMPLETED`, `GOAL_FAILED`, `GOAL_CANCELLED`.
  - `PLAN_CREATED`, `PLAN_STEP_STARTED`, `PLAN_STEP_COMPLETED`, `PLAN_STEP_FAILED`.
  - `AGENT_CREATED`, `AGENT_STARTED`, `AGENT_COMPLETED`, `AGENT_FAILED`.
  - `REPLANNING_STARTED`, `REPLANNING_COMPLETED`.
- **Testing:**
  - 37 new unit and integration tests (190 total, 0 failures, 0 warnings).

### Changed
- `core/contracts/planner.py`: `ExecutionPlan` now has `goal_id` and `agent_id` fields.
- `core/contracts/planner.py`: `TaskStep` now has `retry_count`, `max_retries`, `replan_action`.
- `core/contracts/planner.py`: `PlanResult` now has `failed_step_id` and `replan_action`.
- `core/planner/engine.py`: evolved with replanning support and event publishing.

---

## [0.3.0] - 2026-08-24

### Added
- **Security Hardening Pass (P0 + A1 + A2):**
  - `ConfirmationManager` rewrite: `session_id`/`call_id` binding, `consume(cid, session_id)` single-use, `list_pending()`, `wait_for_confirmation()` preserved.
  - Orchestrator: `confirmed` removed → `approved` param; approve→consume→execute→LLM summary flow; never sets `confirmed=True` internally.
  - MCP: YELLOW/RED return `requires_confirmation` error; GREEN execute normally; `confirmed=False` enforced.
  - StepExecutor and ToolExecutor: `confirmed=True` removed; `operator_direct` replaces `confirmed` param.
  - Chat API: `confirmed` field removed → `approved` field added.
  - `ToolVisibility` enum: `LOCAL_ONLY` (default), `SHARED`.
  - Tools marked SHARED: `echo`, `get_current_time`, `web_search`, `fetch_url`.
  - `ProviderRegistry`: `local: bool` field on `ProviderEntry`; external provider registered `local=False`.
  - `IntelligenceRouter.is_next_provider_local()`: checks top candidate's locality.
  - `ContextBuilder.build_tools_list(shared_only)`: filters tools by visibility for external providers.
  - `security/net_guard.py`: SSRF protection — URL validation, DNS resolution, private IP blocking, redirect hop-by-hop validation, opt-in CIDR via `JARVIS_NET_ALLOW_PRIVATE_NETWORKS`.
  - `FetchUrlTool`: uses net_guard, `follow_redirects=False` with manual redirect loop.
  - `FileTool`: uses `AllowlistValidator.validate_file_path()` with symlink resolution and `relative_to()` containment.
  - Config: `net_allow_private_networks: List[str]` for opt-in LAN access.
- **Test Infrastructure:**
  - `tests/conftest.py`: autouse fixture isolates DB via `tmp_path`, resets all singletons, forces `gc.collect()`.
  - `server/app.py`: lifespan shutdown resets singletons + gc.collect(); hang-at-exit fixed.
- **Testing:**
  - 43 new unit and integration tests (153 total, 0 failures, 0 warnings).

### Changed
- `core/contracts/orchestrator.py`: `OrchestratorRequest.confirmed` removed → `approved: Optional[bool]`.
- `core/orchestrator/tool_executor.py`: `confirmed` param replaced by `operator_direct: bool`.
- `core/contracts/enums.py`: `ToolVisibility` enum added.
- `core/contracts/tool.py`: `visibility` field added to `ToolMetadata` and `BaseTool`.
- `tools/base.py`: `FunctionalTool` accepts `visibility` param.

---

## [0.2.0] - 2026-08-20

### Added
- **Intelligence Router & Multi-Provider Fallback:**
  - `ExternalProvider` — OpenAI-compatible LLM provider via HTTP (`core/llm/external_provider.py`).
  - `ProviderRegistry` — provider registration, health caching with TTL, candidate selection (`core/llm/registry.py`).
  - `IntelligenceRouter` — priority-based routing with automatic fallback (`core/llm/router.py`).
  - `CircuitBreaker` — protects against repeated calls to failed providers.
  - `create_router()` factory function builds IntelligenceRouter from config.
  - Config fields: `external_llm_api_key`, `external_llm_base_url`, `external_llm_model`, `external_llm_provider`.
  - EventBus events: `PROVIDER_SELECTED`, `PROVIDER_FAILED`, `PROVIDER_ONLINE`, `PROVIDER_OFFLINE`, `ROUTING_STARTED`.
  - Orchestrator accepts `router` parameter for backward-compatible routing.
- **Testing:**
  - 41 new unit and integration tests (110 total, 0 failures, 0 warnings).

---

## [0.1.0] - 2026-08-17

### Added
- **Core Architecture & Contracts:**
  - Strict Pydantic v2 data transfer objects (`enums.py`, `telemetry.py`, `tool.py`, `memory.py`, `planner.py`).
  - Centralized settings management with `pydantic-settings` (`core/config.py`).
- **Security & Policy Engine:**
  - Three-tier security model (Green, Yellow, Red) conforming to `AGENTS.md`.
  - Application allowlist validator and dangerous shell metacharacter sanitization (`security/allowlist.py`).
  - Intercepting `PolicyEngine` preventing unauthorized execution or injection attacks.
  - Node authentication via Bearer API keys (`security/auth.py`).
- **Tool System:**
  - Typed and extensible `BaseTool` and `ToolRegistry` (`tools/registry.py`).
  - Built-in tools: `get_system_metrics`, `list_processes`, `launch_application`, `close_application`, `echo`.
- **Windows Agent:**
  - Truthful real-time hardware telemetry collector with NVIDIA GPU discovery (`windows_agent/system.py`).
  - Safe application and process lifecycle manager (`windows_agent/manager.py`).
  - Node agent lifecycle coordinator (`windows_agent/agent.py`).
- **Memory & Storage:**
  - Asynchronous SQLite storage provider (`memory/sqlite_provider.py`).
  - Key-value state persistence with category namespaces.
  - Persistent execution audit trail logging.
- **Planner & State Machine:**
  - Fluent plan definition utility (`core/planner/builder.py`).
  - Task step orchestration engine with dependency management and approval pausing (`core/planner/engine.py`).
- **API Server:**
  - FastAPI server with authenticated routes (`/health`, `/telemetry`, `/tools`, `/tools/execute`).
- **Testing & Documentation:**
  - Automated test suite with 26 comprehensive unit tests.
  - Documentation baseline across `docs/` (`ARCHITECTURE.md`, `SECURITY.md`, `TOOLS.md`, `API.md`, `MEMORY.md`, `ROADMAP.md`).
