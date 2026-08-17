# Changelog

All notable changes to the J.A.R.V.I.S. project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
