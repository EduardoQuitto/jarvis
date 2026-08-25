# J.A.R.V.I.S. — Personal Distributed Intelligence

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-230%20passing-brightgreen.svg)](#testing)
[![Architecture](https://img.shields.io/badge/architecture-modular%20%26%20distributed-green.svg)](#architecture)

J.A.R.V.I.S. is a local, modular, distributed personal AI assistant built with security, portability, and hardware decoupling as core principles.

It is **not** a cloud chatbot. It is a local intelligence layer that runs on your own hardware, talks to your own devices, and follows your own security rules.

---

## Current Status

**Phase 10 complete** (Security & Execution Boundary Hardening). 230 tests passing, 0 failures.

### Implemented

- **Core Architecture**: Pydantic v2 contracts, modular layers, EventBus, central config
- **Tool System**: Typed tools (BaseTool) with ToolRegistry, 12 built-in tools, security classification
- **Security Engine**: PolicyEngine (GREEN/YELLOW/RED), ConfirmationManager, allowlist, anti-SSRF, file sandbox, agent security validation
- **Windows Agent**: Real hardware telemetry collection, GPU detection, process/app management
- **Memory**: SQLite async provider (key-value + audit trail)
- **Planner**: Deterministic plan builder and executor with dependency management
- **Intelligence Router**: Multi-provider fallback with circuit breaker, local/external provider routing
- **REST API**: FastAPI server with /health, /telemetry, /tools, /chat, /mcp endpoints
- **Orchestrator**: LLM-driven agentic loop with tool calling and confirmation flow
- **Goal Engine**: High-level objective lifecycle (create/start/complete/fail/cancel) with replanning
- **Agent System**: Specialized agent execution with immutable permissions, factory, registry, security validation
- **MCP Server**: JSON-RPC 2.0 endpoint for external clients

### In Progress

- **Streaming responses** (SSE from Orchestrator to UI)
- **Conversation persistence** (partially via SQLite)

### Planned (Not Yet Implemented)

- **Home Assistant integration** (scheduler, automations, Wake-on-LAN)
- **Voice pipeline** (Wake Word -> VAD -> STT -> TTS)
- **Android/Tablet dashboard** (Home Assistant Companion + lightweight HTML panel)
- **Computer Vision** (screenshot, OCR, visual analysis)
- **Semantic/vector memory** (embeddings, Mem0, Cognee — evaluation pending)
- **Production security** (CORS hardening, rate limiting, API key rotation)

### Experimental

- **GoalOrchestrator**: Routes complex requests to GoalEngine using keyword heuristics. The complexity detection is simple and may misclassify requests. Full integration with the main Orchestrator requires further testing.
- **Replanning**: Based on retry count and predefined strategies. LLM-driven replanning is not yet implemented.
- **Agent Factory**: Creates predefined agent types. Inter-agent dependencies and shared memory between agents are not yet supported.

---

## Architecture

```
+-------------------------------------------------------------------+
|                        JARVIS Server (i3)                         |
|  Home Assistant / Docker / Scheduler / Wake-on-LAN / Gateway      |
+-------------------------------------------------------------------+
        |                                    |
        v                                    v
+-------------------+          +---------------------------+
| Windows Agent     |          | JARVIS Core (planned)     |
| (i5-7400 dev)     |          | (i5-14400 / 32 GB)        |
| Telemetry / Apps  |          | LLM / STT / TTS / Vision  |
+-------------------+          +---------------------------+

+-------------------------------------------------------------------+
|                        Core Architecture                          |
+-------------------------------------------------------------------+

  User Request
       |
       v
  [Chat API] --> [Orchestrator] --> [PolicyEngine] --> GREEN: execute
       |              |                    |           YELLOW: confirm
       |              v                    v           RED: block
       |         [LLM / Router]      [ConfirmationMgr]
       |              |
       |              v
       |     [IntelligenceRouter]
       |        |            |
       |        v            v
       |   [Local LLM]  [External LLM]
       |   (Ollama)     (Groq, Together...)
       |
       v
  [ToolRegistry] --> [Tools]
       |                |
       |     +----------+----------+
       |     |          |          |
       v     v          v          v
  [Agent System]  [Goal Engine]  [Planner]
       |              |              |
       v              v              v
  [AgentFactory] [GoalEngine]  [PlanBuilder]
  [AgentRegistry]              [PlanExecutor]
  [AgentSecurity]              [ReplanCallback]
       |              |              |
       +--------------+--------------+
                      |
                      v
               [SQLite Memory]
               [EventBus]
```

### Component Relationships

| Component | Role | Key Files |
|-----------|------|-----------|
| **Chat API** | Entry point for user messages | `server/routers/chat.py` |
| **Orchestrator** | LLM-driven agentic loop | `core/orchestrator/engine.py` |
| **PolicyEngine** | Security classification (GREEN/YELLOW/RED) | `security/policy_engine.py` |
| **ConfirmationManager** | Single-use, session-bound confirmations | `core/orchestrator/confirmation.py` |
| **IntelligenceRouter** | Multi-provider fallback with circuit breaker | `core/llm/router.py` |
| **ProviderRegistry** | Provider health, locality, candidate selection | `core/llm/registry.py` |
| **ToolRegistry** | Typed tool registration and execution | `tools/registry.py` |
| **Agent System** | Isolated agent execution with permissions | `core/agent/agent.py` |
| **AgentFactory** | Dynamic agent creation with security validation | `core/agent/factory.py` |
| **GoalEngine** | High-level objective lifecycle | `core/goal/engine.py` |
| **Planner** | Deterministic plan building and execution | `core/planner/engine.py` |
| **SQLite Memory** | Key-value persistence + audit trail | `memory/sqlite_provider.py` |
| **EventBus** | System-wide event publishing | `core/events/bus.py` |
| **NetGuard** | Anti-SSRF protection | `security/net_guard.py` |
| **Windows Agent** | Native telemetry and process management | `windows_agent/` |

---

## Hardware

### Current Development Setup

| Node | Hardware | Role |
|------|----------|------|
| **JARVIS Server** | Intel Core i3-3220, 8 GB RAM, Ubuntu Server | 24/7 gateway, Home Assistant, automations, scheduler |
| **NODE 2 (dev)** | Intel Core i5-7400, 8 GB RAM, SSD ~222 GB + HDD 500 GB, GTX 650 Ti | Development machine, testing, auxiliary tasks |

> **Note:** NODE 2 was originally a Pentium G3260. It has been upgraded to an i5-7400. The codebase is designed to be portable and not optimized for any specific hardware.

### Planned Hardware

| Node | Hardware | Role |
|------|----------|------|
| **JARVIS Core** | Intel Core i5-14400, 32 GB RAM, SSD NVMe 1 TB | LLM (Ollama), STT, TTS, vision, heavy processing |
| **JARVIS Mobile** | Samsung Galaxy S20 FE | Voice, notifications, sensors, ADB |
| **JARVIS Panel** | Samsung Galaxy Tab E | Lightweight dashboard, telemetry |

---

## Installation

### Prerequisites

- **Python 3.13+** ([download](https://www.python.org/downloads/))
- **Git** ([download](https://git-scm.com/downloads))

If Git is not installed on Windows, download it from https://git-scm.com/downloads and run the installer. On Linux:
```bash
sudo apt install git    # Debian/Ubuntu
sudo pacman -S git      # Arch
```

### Step-by-Step Setup

```bash
# 1. Clone the repository
git clone https://github.com/EduardoQuitto/jarvis.git
cd jarvis

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# 4. Install dependencies
pip install -e .

# 5. Configure environment variables
Copy-Item .env.example .env
# Then edit .env with your settings (see below)

# 6. Run the tests to verify everything works
pytest -v

# 7. Start the server
python -m uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

### Environment Configuration

The `.env.example` file is a **template only**. It must be copied to `.env` and customized.

**Critical: Never put real API keys, tokens, or passwords in `.env.example` or commit them to git.**

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_API_KEY` | `jarvis-dev-insecure-key-change-me` | **Change this** in any non-local environment |
| `JARVIS_LLM_PROVIDER` | `mock` | `mock` for dev, `ollama` for local LLM, `external` for cloud |
| `JARVIS_EXTERNAL_LLM_API_KEY` | *(empty)* | Required if using Groq, Together, OpenRouter, etc. |
| `JARVIS_DB_PATH` | `./data/jarvis.db` | SQLite database path |
| `JARVIS_LOG_LEVEL` | `INFO` | Logging verbosity |

> **Future improvement:** Auto-generating a secure `.env` with random API keys on first run is planned but not yet implemented.

---

## Security

JARVIS enforces a strict three-tier security model. No component — including LLM, MCP, or agents — can bypass these rules.

### Security Levels

- **GREEN**: Auto-executed. System queries, process lists, time, echo. No user confirmation needed.
- **YELLOW**: Requires confirmation. App launch/close, file read/write, directory listing. ConfirmationManager issues a single-use, session-bound token.
- **RED**: Requires explicit authorization. File deletion, firewall changes, credential modifications.

### Security Components

| Component | Purpose |
|-----------|---------|
| **PolicyEngine** | Classifies every tool action as GREEN/YELLOW/RED before execution |
| **ConfirmationManager** | Issues and consumes single-use confirmation tokens bound to session_id |
| **ToolVisibility** | `LOCAL_ONLY` (default) vs `SHARED`. External LLMs only see SHARED tools |
| **AgentSecurityValidator** | Enforces immutable permissions on agents; prevents privilege escalation |
| **NetGuard** | Anti-SSRF: blocks private IPs, validates redirects, DNS resolution checks |
| **File Sandbox** | AllowlistValidator with symlink resolution and path containment |
| **AllowlistValidator** | App name allowlist + dangerous metacharacter sanitization |

### What Agents Cannot Do

- Grant themselves permissions
- Bypass the PolicyEngine
- Set `confirmed=True` on tool calls
- Access tools outside their allowlist
- Modify security policies

---

## Memory

JARVIS uses **SQLite** (via `aiosqlite`) as its persistence layer:

- **Key-value store** (`memory_store`): System state, preferences, configuration
- **Audit trail** (`audit_logs`): Every tool execution logged with timestamp, node, parameters, success/failure

SQLite was chosen for its zero-configuration, low resource usage, and suitability for the current hardware (i3 server, i5 dev machine).

**Semantic/vector memory** (embeddings, Mem0, Cognee, or similar) is a planned future capability for the JARVIS Core node (i5-14400). It has not been implemented yet and is under evaluation. SQLite will remain the foundational persistence layer.

---

## Provider Routing

JARVIS is designed to use **local and external LLM providers** based on availability, capability, and security policy.

```
User Request --> IntelligenceRouter
                    |
         +----------+----------+
         |                     |
    [Local Provider]     [External Provider]
    (Ollama on LAN)      (Groq, Together, OpenRouter)
         |                     |
    All tools visible    Only SHARED tools visible
    (LOCAL_ONLY + SHARED)   (echo, time, web_search, fetch_url)
```

- **IntelligenceRouter** handles fallback, circuit breaker, and scoring
- **ProviderRegistry** tracks provider health, locality (`local: bool`), and capabilities
- **ContextBuilder** filters tool visibility: external providers never see local-only tools

This architecture allows the system to operate fully offline (local LLM) or leverage cloud providers when available, without exposing sensitive system tools to external services.

---

## Testing

```bash
# Run the full test suite
pytest -v

# Run quietly (summary only)
pytest -q --no-header -p no:cacheprovider

# Run a specific test file
pytest tests/unit/test_goal_engine.py -v
```

**230 tests** across unit and integration suites:
- Unit tests: contracts, config, planner, memory, security, tools, router, agents, goals
- Integration tests: AI pipeline, E2E pipeline, multi-provider flow, goal-agent integration

The test database (`data/jarvis.db`) is **never touched** by tests. Each test runs in an isolated temporary directory.

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/AGENTS.md`](docs/AGENTS.md) | Permanent project rules and constraints |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Software architecture and module breakdown |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security model, confirmation flow, SSRF protection |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Tool system, built-in tools, agent types |
| [`docs/API.md`](docs/API.md) | REST API specification (endpoints, schemas, examples) |
| [`docs/MEMORY.md`](docs/MEMORY.md) | SQLite persistence layer and schema |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Development roadmap and phase tracking |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Hardware specifications and topology |
| [`docs/TESTING.md`](docs/TESTING.md) | Test suite guide |
| [`docs/NETWORK.md`](docs/NETWORK.md) | Network topology |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment and server setup |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make your changes following the project's coding standards (see `docs/AGENTS.md`)
4. Run the full test suite: `pytest -v`
5. Ensure all 230 tests pass with 0 failures
6. Commit your changes with a clear message
7. Push and open a Pull Request

**Before implementing large changes:** Read `docs/AGENTS.md` Section 23 ("Comportamento do agente"). Study the repository, check architecture, identify impact, and propose a plan first.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built as a personal distributed intelligence system. Not a toy, not a chatbot — a real infrastructure layer for local AI.
