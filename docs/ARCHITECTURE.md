# J.A.R.V.I.S. — Architecture

## 1. Overview

JARVIS is designed as a distributed, decoupled, contract-oriented architecture, ensuring portability across hardware nodes and operating systems.

```mermaid
graph TD
    subgraph "User Interface"
        ChatAPI["server/routers/chat.py (Chat API)"]
        MCP["server/routers/mcp.py (MCP Server)"]
    end

    subgraph "Core & Orchestration"
        Config["core.config (Pydantic Settings)"]
        Contracts["core.contracts (DTOs & Enums)"]
        Orchestrator["core.orchestrator (Orchestrator + GoalOrchestrator)"]
        EventBus["core.events.bus (EventBus)"]
    end

    subgraph "Intelligence & Planning"
        Router["core.llm.router (IntelligenceRouter)"]
        ProviderReg["core.llm.registry (ProviderRegistry)"]
        Planner["core.planner (PlanBuilder + PlanExecutor)"]
        GoalEngine["core.goal.engine (GoalEngine)"]
    end

    subgraph "Agent System"
        AgentFactory["core.agent.factory (AgentFactory)"]
        AgentRegistry["core.agent.registry (AgentRegistry)"]
        AgentSec["core.agent.security (AgentSecurityValidator)"]
        Agent["core.agent.agent (Agent)"]
    end

    subgraph "Security"
        PolicyEngine["security.policy_engine (PolicyEngine)"]
        ConfirmMgr["core.orchestrator.confirmation (ConfirmationManager)"]
        Allowlist["security.allowlist (AllowlistValidator)"]
        NetGuard["security.net_guard (NetGuard)"]
        Auth["security.auth (RequireNodeAuth)"]
    end

    subgraph "Tools & Execution"
        ToolRegistry["tools.registry (ToolRegistry)"]
        BuiltinTools["tools.builtin (12 built-in tools)"]
        WinAgent["windows_agent (WindowsAgent)"]
    end

    subgraph "Persistence"
        Memory["memory.sqlite_provider (SQLiteMemoryProvider)"]
        Server["server.app (FastAPI)"]
    end

    ChatAPI --> Orchestrator
    MCP --> Orchestrator
    Orchestrator --> PolicyEngine
    Orchestrator --> Router
    Orchestrator --> GoalEngine
    GoalEngine --> AgentFactory
    GoalEngine --> Planner
    AgentFactory --> Agent
    Agent --> ToolRegistry
    Agent --> AgentSec
    Router --> ProviderReg
    Planner --> ToolRegistry
    Planner --> Memory
    ToolRegistry --> PolicyEngine
    PolicyEngine --> ConfirmMgr
    ToolRegistry --> BuiltinTools
    BuiltinTools --> WinAgent
    PolicyEngine --> Allowlist
    BuiltinTools --> NetGuard
    Server --> Auth
    EventBus --> Orchestrator
    EventBus --> GoalEngine
    EventBus --> Router
```

---

## 2. Module Breakdown

| Module | Responsibility | OS-Agnostic? |
|--------|---------------|--------------|
| `core/contracts` | Interfaces, DTOs, enums | Yes (100%) |
| `core/config` | Centralized settings (Pydantic) | Yes (100%) |
| `core/events` | System-wide event bus | Yes (100%) |
| `core/orchestrator` | LLM-driven agentic loop, confirmation flow | Yes (100%) |
| `core/planner` | Deterministic plan building and execution | Yes (100%) |
| `core/goal` | High-level objective lifecycle and replanning | Yes (100%) |
| `core/agent` | Agent execution, factory, registry, security | Yes (100%) |
| `core/llm` | LLM providers, routing, circuit breaker | Yes (100%) |
| `core/conversation` | Conversation context building | Yes (100%) |
| `core/mcp` | MCP server (JSON-RPC 2.0) | Yes (100%) |
| `core/task` | Task management and execution | Yes (100%) |
| `security/` | PolicyEngine, allowlist, auth, SSRF protection | Yes (100%) |
| `tools/` | Typed tool registration and execution | Yes (100%) |
| `memory/` | SQLite async persistence + audit trail | Yes (100%) |
| `server/` | FastAPI REST server and endpoints | Yes (100%) |
| `windows_agent/` | Native Windows telemetry and process management | Windows only |

---

## 3. Core Contracts

1. **`BaseTool`**: Every system action inherits from `BaseTool` with Pydantic input schema and `ToolResult` output.
2. **`ToolResult`**: Standardized output: `success: bool`, `data: Any`, `error: Optional[str]`, `execution_time_ms: float`, `security_level: SecurityLevel`.
3. **`BaseMemoryProvider`**: Async interface for key-value storage and audit entries (`AuditEntry`).
4. **`ExecutionPlan` & `TaskStep`**: Sequential, dependency-oriented task orchestration structure.
5. **`Goal`**: High-level objective with lifecycle (pending → running → completed/failed/cancelled).
6. **`AgentSpec`**: Agent specification with identity, permissions, and tool/provider allowlists.
7. **`AgentPermission`**: Immutable permission set controlling what an agent can do.

---

## 4. Security Architecture

### AuthorizationBoundary (Phase 10)
All tool execution flows through a single authorization boundary:
- **PolicyEngine** requires `source` parameter: `"operator"`, `"orchestrator"`, `"mcp"`, `"plan_executor"`, `"step_executor"`, `"agent"`.
- **Untrusted sources** (MCP, planner, step_executor, agent) have `confirmed=True` silently ignored.
- **RED actions** require `source="operator"` only — orchestrator and all other sources cannot confirm RED.
- **YELLOW actions** from untrusted sources always require confirmation (operator path).

### Tool Visibility
- **ToolVisibility** (`LOCAL_ONLY` / `SHARED`) prevents external LLMs and MCP from seeing local-only tools.
- MCP `tools/list` returns only SHARED tools; `tools/call` blocks LOCAL_ONLY.

### Other Security Components
- **ConfirmationManager** issues single-use, session-bound tokens for YELLOW/RED actions with timestamps, expiry, and reuse blocking.
- **AgentSecurityValidator** enforces immutable permissions on agents — agents cannot escalate privileges.
- **AgentToolExecutor** validates permissions at execution time for every tool call.
- **NetGuard** blocks SSRF attacks: private IP blocking, cloud metadata IPs (`169.254.169.254`, `169.254.169.253`), DNS validation, redirect hop-by-hop checking, `metadata.google.internal` hostname blocking.
- **AllowlistValidator** prevents directory traversal and validates file paths with symlink resolution.
- **CORS** configured via `JARVIS_CORS_ORIGINS` env var; production defaults to same-origin only.
