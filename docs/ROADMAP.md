# J.A.R.V.I.S. — Roadmap de Desenvolvimento

## Fases do Projeto

### ✅ Fase 1: Fundação & Contratos (Concluída)
- [x] Modelagem de contratos tipados com Pydantic v2 (`core/contracts/`).
- [x] Gerenciamento de configurações com Pydantic Settings (`core/config.py`).
- [x] Ambiente portátil configurado e suite de testes base com `pytest`.

### ✅ Fase 2: Tool System & Security Engine (Concluída)
- [x] Níveis de segurança Verde, Amarelo e Vermelho (`security/levels.py`).
- [x] Validador de allowlist e sanitização de injeção de comandos (`security/allowlist.py`).
- [x] `PolicyEngine` para interceptação e bloqueio de ações não autorizadas.
- [x] `ToolRegistry` e ferramentas built-in tipadas.

### ✅ Fase 3: Windows Agent Core (Concluída)
- [x] Coleta real de telemetria de hardware (`WindowsSystemCollector`).
- [x] Suporte a detecção de GPU NVIDIA (`nvidia-smi`).
- [x] Gerenciador de processos e aplicações controladas (`WindowsAppManager`).
- [x] Coordenação de ciclo de vida do agente (`WindowsAgent`).

### ✅ Fase 4: API REST & Segurança de Rede (Concluída)
- [x] Servidor FastAPI com rotas `/health`, `/telemetry` e `/tools/execute`.
- [x] Middleware e dependência de autenticação por token de nó (`security/auth.py`).

### ✅ Fase 5: Camada de Memória SQLite (Concluída)
- [x] Provedor de armazenamento assíncrono `SQLiteMemoryProvider`.
- [x] Armazenamento de estado chave-valor estruturado.
- [x] Trilha de auditoria persistente de execução de ferramentas.

### ✅ Fase 6: Planner Determinístico & State Machine (Concluída)
- [x] Construtor fluente de planos `PlanBuilder`.
- [x] Executor sequencial e orientado a dependências `PlanExecutor`.
- [x] Pausa automática de planos para aprovação de usuário (`REQUIRE_APPROVAL`).

### ✅ Fase 7: Intelligence Router & Multi-Provider (Concluída)
- [x] `ExternalProvider` — provedor LLM externo compatível com OpenAI (`core/llm/external_provider.py`).
- [x] `ProviderRegistry` — registro, cache de saúde e seleção de candidatos (`core/llm/registry.py`).
- [x] `IntelligenceRouter` — roteamento com fallback, circuit breaker e scoring (`core/llm/router.py`).
- [x] `CircuitBreaker` — proteção contra chamadas repetidas a provedores com falha.
- [x] Fábrica de provedores estendida com `"external"` e `create_router()` (`core/llm/factory.py`).
- [x] Configuração de provedor externo via variáveis de ambiente (`core/config.py`).
- [x] Orchestrator aceita `IntelligenceRouter` ou `BaseLLMProvider` (compatibilidade retroativa).
- [x] Chat API usa `IntelligenceRouter` por padrão.
- [x] Eventos `PROVIDER_SELECTED`, `PROVIDER_FAILED`, `ROUTING_STARTED` no EventBus.
- [x] 41 novos testes (total: 110 testes, 0 falhas, 0 warnings).

### ✅ Fase 8: Security Hardening (Concluída)
- [x] Confirmação corrigida: `confirmed` removido do Orchestrator/Chat API → `approved`.
- [x] ConfirmationManager: `session_id`/`call_id` vinculados, `consume()` single-use.
- [x] MCP: YELLOW/RED retornam `requires_confirmation` ao cliente; GREEN executam.
- [x] StepExecutor e ToolExecutor: `confirmed=True` removido.
- [x] `ToolVisibility` enum: `LOCAL_ONLY` (padrão), `SHARED`.
- [x] Tools SHARED: `echo`, `get_current_time`, `web_search`, `fetch_url`.
- [x] ProviderRegistry: campo `local: bool` em `ProviderEntry`.
- [x] IntelligenceRouter: `is_next_provider_local()` para filtro de visibilidade.
- [x] ContextBuilder: `build_tools_list(shared_only)` filtra por visibility.
- [x] Orchestrator: usa router para filtrar tools antes de chamar LLM externo.
- [x] `security/net_guard.py`: anti-SSRF com validação de URL, DNS, redirect hop-by-hop.
- [x] FetchUrlTool: usa net_guard, `follow_redirects=False` com redirect manual.
- [x] FileTool: usa `AllowlistValidator.validate_file_path()` com symlink resolution.
- [x] Config: `net_allow_private_networks` para opt-in de LAN.
- [x] Test infrastructure: DB isolamento via `tmp_path`, singleton resets, gc.collect().
- [x] 43 novos testes (total: 153 testes, 0 falhas, 0 warnings).

### ✅ Fase 9: Goal Engine + Agent System (Concluída)
- [x] Goal Engine: `core/goal/engine.py` — lifecycle de goals com replanning.
- [x] Goal contracts: `core/contracts/goal.py` — Goal, GoalResult, GoalStatus, ReplanDecision.
- [x] Agent contracts: `core/contracts/agent.py` — AgentSpec, AgentState, AgentResult, AgentPermission.
- [x] Agent System: `core/agent/agent.py` — executor isolado com permissões imutáveis.
- [x] Agent Registry: `core/agent/registry.py` — tracking de agentes ativos.
- [x] Agent Factory: `core/agent/factory.py` — criação dinâmica com validação de segurança.
- [x] Agent Security: `core/agent/security.py` — validação de permissões e restrições.
- [x] Planner evoluído: `core/planner/engine.py` — replanning com ReplanCallback.
- [x] Orchestrator Goal Integration: `core/orchestrator/goal_integration.py` — roteamento inteligente.
- [x] Novos enums: `GoalStatus`, `AgentStatus`, `ReplanAction` em `core/contracts/enums.py`.
- [x] Novos eventos: GOAL_*, PLAN_*, AGENT_*, REPLANNING_* no EventBus.
- [x] 37 novos testes (total: 193 testes, 0 falhas, 0 warnings).

### Limitações Conhecidas da Fase 9

* **GoalEngine**: A detecção de complexidade usa heurística por palavras-chave (pode classificar incorretamente requests simples como complexos e vice-versa).
* **Replanning**: Baseado em retry count e estratégias predefinidas. Replanejamento guiado por LLM ainda não foi implementado.
* **Agent Factory**: Cria tipos predefinidos de agentes. Dependências entre agentes e memória compartilhada entre agents não são suportadas.
* **GoalOrchestrator**: Wrapper sobre o Orchestrator existente. A integração completa com o Orchestrator original requer testes de end-to-end adicionais.
* **Agentes**: São task-scoped (temporários) e não possuem memória persistente entre execuções.

---

### Próximas Fases (Futuras)

* **Fase 10: Streaming de Respostas** (SSE streaming do Orchestrator para UI, chunks de texto em tempo real).
* **Fase 11: Persistência de Conversas** (Garantir que conversas sobrevivam a restarts do servidor — já parcialmente implementado via SQLite).
* **Fase 12: Segurança de Produção** (CORS, rate limiting, validação de chave de API em produção).
* **Fase 13: Integração Home Assistant** (Scheduler, automações e Wake-on-LAN no JARVIS Server).
* **Fase 14: Pipeline de Voz Local** (Wake Word -> VAD -> Whisper -> TTS Piper).
* **Fase 15: Android & Tablet Dashboard** (Home Assistant Companion + painel HTML ultraleve).
* **Fase 16: Visão Computacional** (Captura de tela, OCR e análise visual local).
* **Fase 17: Memória Vetorial & Busca Semântica** (Embeddings locais no i5-14400).

---

### Nota sobre Hardware

O NODE 2 foi originalmente um Pentium G3260. Foi atualizado para um i5-7400 com 8 GB RAM, SSD ~222 GB e HDD 500 GB. O código é projetado para ser portátil e não é otimizado para hardware específico.
