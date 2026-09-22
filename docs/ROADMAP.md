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

### ✅ Fase 10: Segurança e Reforço dos Limites de Execução (Concluída)
- [x] AuthorizationBoundary: PolicyEngine reescrito com parâmetro `source`.
- [x] `UNTRUSTED_SOURCES`, `YELLOW_CAPABLE_SOURCES`, `OPERATOR_SOURCES` definidos.
- [x] `source` propagação: ToolRegistry → ToolExecutor → Orchestrator.
- [x] Orchestrator NUNCA passa `confirmed=True` do caminho LLM.
- [x] Caminho confirmado usa `source="operator"` — único que pode confirmar YELLOW/RED.
- [x] MCP Hardening: `tools/list` retorna apenas SHARED; `tools/call` bloqueia LOCAL_ONLY.
- [x] PlanExecutor/StepExecutor: `confirmed_steps` removido, `source` propagado.
- [x] Agent Security: `AgentToolExecutor` com validação de permissões por chamada.
- [x] NetGuard: cloud metadata IP ranges (`169.254.169.254`, `169.254.169.253`) e hostname `metadata.google.internal` bloqueados.
- [x] CORS: configuração via `JARVIS_CORS_ORIGINS`, production same-origin only.
- [x] ConfirmationManager: timestamps, cleanup de expirados, bloqueio de reuse, log de tentativas.
- [x] 28 novos testes adversariais (total: 230 testes, 0 falhas, 0 warnings).

### Limitações Conhecidas da Fase 10

* **Source parameter**: Todos os chamadores precisam propagar `source` corretamente — callers legados sem source receberão o padrão `"orchestrator"`.
* **Agent isolation**: Agentes usam ConfirmationManager isolado, mas não possuem memória persistente entre execuções.
* **CORS**: Em desenvolvimento, permite `http://localhost:3000` por padrão. Em produção, same-origin only (nenhum CORS headers).

### Ponte CORE ↔ SERVER + Presença (Em operação)
- [x] `RemoteNodeClient` — transporte HTTP CORE → SERVER (`/health`, `/tools`, `/tools/execute`), erros padronizados.
- [x] `remote_server_tool` — proxy controlado: somente tools SHARED, `confirmed=False`, LOCAL_ONLY sempre bloqueado.
- [x] `NodePresenceManager` — auto-registro (`POST /api/devices/`) + heartbeat (`POST /api/devices/heartbeat`) a cada 30s (configurável via `JARVIS_SERVER_HEARTBEAT_INTERVAL`).
- [x] SERVER offline não impede o funcionamento local do Core (Ollama + tools locais); retry no próximo ciclo, sem retry agressivo.
- [x] IP/porta anunciados somente via `JARVIS_NODE_ADVERTISE_IP` / `JARVIS_NODE_ADVERTISE_PORT` (nenhum endpoint de entrada inventado).
- [x] Task Bridge (`DistributedTaskClient` + 7 métodos no `RemoteNodeClient`): Core cria/consulta/atualiza/completa/falha/cancela/pausa/retoma tasks persistidas no SERVER (`device_id="jarvis-core"`). `PATCH error` traduzido para o histórico `errors` (sem coluna nova, sem schema change). Lifecycle apenas — sem worker/scheduler/queue.
- [x] Google AI Studio (Gemini) como fallback cloud reutilizando `ExternalProvider` (`JARVIS_GOOGLE_*`, slot `google` priority 7, `local=False`); Ollama segue primário (10), mock por último (1). Cloud só enxerga tools SHARED.
- [x] Retry com backoff no `ExternalProvider.generate()` (3 tentativas, ~1s/~2s) para 408/429/500/502/503/504; 4xx permanentes nunca retentam; streaming inalterado.
- [x] Fluxo de confirmação corrigido: aprovação consumida é propagada (`operator_direct`) e falha de tool aprovada nunca é relatada como "Action completed.".

---

### ✅ Fase 12: Central Server & Central State Authority (Concluída)

SERVER = control plane / source of truth. CORE = compute plane (Orchestrator, LLM, tools locais).

- [x] `CentralStateClient` (`core/network/central_state_client.py`) sobre `RemoteNodeClient`: conversas, memória e confirmações via HTTP, erros explícitos (`CentralStateError`), nada inventado. Flags `JARVIS_CENTRAL_STATE_ENABLED` (default off, modo local preservado) e `JARVIS_CENTRAL_STATE_REQUIRED` (falha explícita, sem fallback silencioso).
- [x] Conversas centrais: `POST/GET /api/conversations/`, `GET /{id}`, `GET/POST /{id}/messages` sobre o schema SQLite existente; `ConversationManager` aceita backend central (sequência `user -> assistant(tool_calls) -> tool -> assistant` preservada).
- [x] Memória central: `CentralMemoryProvider` (mesma interface `BaseMemoryProvider` + `search_memory`); `search_memory` tool usa o backend do runtime. Sem vetores/embeddings.
- [x] Confirmações centrais: tabela `confirmations` + `POST/GET /api/confirmations/`, `/pending`, `/{id}`, `/{id}/resolve`, `/{id}/consume` (atômico, single-use), `/cleanup`; single-use, session binding, expiry, approved/denied e `remaining_calls` preservados.
- [x] Gateway: em `node_role=SERVER`, `POST /api/chat/send|/stream` encaminha a um CORE elegível (type CORE + capability LLM + ONLINE/READY + ip/porta); HTTP 503 explícito sem CORE; sem mock, sem resposta inventada. Demais roles respondem localmente como antes.
- [x] Compute interno: `POST /internal/chat/send|/stream` (auth obrigatória, recusado em role SERVER) reutilizando
  exatamente o Orchestrator; proxy SSE byte a byte, sem órfãs.
- [x] Gemini via SERVER: chave somente no SERVER; relay `POST /api/llm/chat/completions` (+ `/models`, streaming); CORE acessa via relay sem possuir a chave; `search_memory` com fallback local em modo não-required e falha explícita em modo required.
- [ ] Acesso externo futuro via rede privada/VPN (não implementado; arquitetura já separa gateway SERVER de compute CORE).
- [x] Descoberta via `DeviceRegistry` existente (`/api/devices/` agora expõe ip/porta/capabilities/status); V1 seleciona o primeiro elegível, sem fila/scheduler/workers.

#### ✅ Validação operacional da Fase 12 (Concluída)

SERVER = control plane / source of truth; CORE = compute plane. Resultados verificados contra hardware real:

- [x] SERVER Ubuntu (`jarvisserver`, LAN `192.168.0.13`): `jarvis.service` funcionando, FastAPI/Uvicorn em `0.0.0.0:8000`, `/health` retornando `healthy` (serviço parado e reiniciado durante a validação).
- [x] CORE Windows (LAN `192.168.0.8`): Ollama funcionando com `qwen3.5:4b`; auto-registro no SERVER + heartbeat periódico; SERVER identifica o dispositivo como `CORE` com capacidade `llm`.
- [x] Fluxo distribuído real cliente -> SERVER -> CORE -> Ollama -> SERVER -> cliente via `POST /api/chat/send`, com resposta real recebida; SERVER retorna HTTP 503 sem CORE elegível e o fluxo volta após a recuperação do CORE.
- [x] Conversas centralizadas: mensagens persistidas no SERVER, sequência user -> assistant/tool call -> tool result -> assistant final verificada.
- [x] Memória central: CORE com `CentralMemoryProvider`, escrita/leitura via estado central, valor de teste recuperado corretamente.
- [x] Confirmações centralizadas: criação, aprovação, consumo pelo CORE, single-use (segunda tentativa bloqueada), session binding/expiração funcionando.
- [x] Gemini: chave real somente no SERVER (CORE sem a chave), acesso via relay do SERVER, `gemini-3.5-flash-lite` validado com geração real (health + generation OK).
- [x] Streaming: `POST /api/chat/stream` (`text/event-stream`) com eventos `start`, `thinking`, `tool_call`, `tool_result`, `text_delta` e `done`; resposta final persistida no SERVER; desconexão do cliente sem traceback/ERROR nos logs do SERVER.
- [x] Task Bridge: criação, consulta, atualização de progresso, conclusão e leitura do estado final via lifecycle remoto.
- [x] Segurança/repositório: `.env` não versionado (só `.env.example`); nenhuma chave Gemini real no Git; `.gitignore` protege `.env`, bancos e ambientes virtuais.
- [x] Testes da fase: 440 coletados, 438 passando, 0 falhas, 2 skips; `compileall` limpo; `git diff --check` limpo.

Acesso externo (fora de casa) continua futuro e não implementado: quando existir, será cliente externo -> rede privada segura/VPN -> SERVER -> CORE, nunca exposição direta à internet pública. Fases futuras (voz, Android, visão, Home Assistant) seguem não implementadas.

### Próximas Fases (Futuras)

* **Fase 11: Streaming de Respostas** (Concluída) — `Orchestrator.stream_message()` emite eventos estruturados (`start`, `thinking`, `text_delta`, `tool_call`, `tool_result`, `waiting_confirmation`, `error`, `done`) via `POST /api/chat/stream` (SSE `text/event-stream`); mesmos gates de PolicyEngine/ToolExecutor/ConfirmationManager e mesma persistência do `/api/chat/send`; tool calls continuam buffered internamente; disconnect do cliente cancela sem órfãs.
* **Fase 13: Integração Home Assistant** (Scheduler, automações e Wake-on-LAN no JARVIS Server).
* **Fase 14: Pipeline de Voz Local** (Wake Word -> VAD -> Whisper -> TTS Piper).
* **Fase 15: Android & Tablet Dashboard** (Home Assistant Companion + painel HTML ultraleve).
* **Fase 16: Visão Computacional** (Captura de tela, OCR e análise visual local).
* **Fase 17: Memória Vetorial & Busca Semântica** (Embeddings locais no i5-14400).
* **Fase 18: Autonomia Progressiva** (Agentes autônomos com limites de execução, orçamento de tokens e supervisão humana).

---

### Nota sobre Hardware

O NODE 2 foi originalmente um Pentium G3260. Foi atualizado para um i5-7400 com 8 GB RAM, SSD ~222 GB e HDD 500 GB. O código é projetado para ser portátil e não é otimizado para hardware específico.
