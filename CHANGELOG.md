# Changelog

All notable changes to the J.A.R.V.I.S. project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
