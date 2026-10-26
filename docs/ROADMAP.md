# J.A.R.V.I.S. — Roadmap de Desenvolvimento

## Ressalva — Visão de Produto e Distribuição

O J.A.R.V.I.S. está sendo desenvolvido com perspectiva de evolução futura para um produto distribuível e comercializável, podendo ser disponibilizado para empresas e consumidores finais.

As decisões de arquitetura e implementação devem, sempre que possível, preservar essa possibilidade de evolução, evitando dependências desnecessárias de uma máquina, ambiente ou configuração exclusivamente local.

A visão futura inclui:

- sistema de contas e autenticação de usuários;
- interface para conectar e gerenciar provedores e serviços externos, seguindo um modelo semelhante ao fluxo de conexão de provedores utilizado por ferramentas como o OpenCode;
- gerenciamento de credenciais e configurações pela interface, reduzindo a dependência de edição manual de arquivos `.env`;
- instalador do J.A.R.V.I.S. responsável por configurar automaticamente o ambiente, dependências, configurações, inicialização e componentes necessários;
- distribuição para **Windows, Linux e macOS**;
- instalação simplificada do **SERVER**, preferencialmente através de Docker;
- possibilidade de distribuição do projeto como código, serviço para empresas ou produto destinado a consumidores finais.

Esta visão não altera o escopo da fase atual nem antecipa a implementação desses recursos. Ela deve servir como **restrição arquitetural e direção de longo prazo**, para que decisões tomadas nas fases atuais não dificultem a futura transformação do J.A.R.V.I.S. em um produto instalável e distribuível.

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

#### ⚠️ Planned extension — Neural Load Balancer v1 (futuro, D)
- [ ] Estender o scoring com sinais reais de telemetria (CPU, RAM, latência) e capacidade do modelo, sem criar um segundo roteador.
- [ ] Migração live de tarefas em execução está explicitamente fora do escopo (arquitetura stateless, sem motor de migração).

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

#### ⚠️ Planned extension — Adaptive Security Posture (futuro, HIGH-RISK, F)
- [ ] Hook determinístico versionado sobre o PolicyEngine, somente após volume de auditoria/observabilidade (Phase 23).
- [ ] Garantias obrigatórias: regras determinísticas; somente escalada GREEN para postura mais restritiva; LLM nunca aumenta permissões nem altera a própria autorização; fail-safe para o mais restritivo; expiração automática; toda mudança em `audit_logs`; override explícito do operador.
- [ ] Testes adversariais obrigatórios (prompt injection tentando afrouxar a postura deve falhar).
- [ ] Nunca expor como tool ao LLM.

### Limitações Conhecidas da Fase 10

* **Source parameter**: Todos os chamadores precisam propagar `source` corretamente — callers legados sem source receberão o padrão `"orchestrator"`.
* **Agent isolation**: Agentes usam ConfirmationManager isolado, mas não possuem memória persistente entre execuções.
* **CORS**: Em desenvolvimento, permite `http://localhost:3000` por padrão. Em produção, same-origin only (nenhum CORS headers).

### Ponte CORE ↔ SERVER + Presença (Em operação)
- [x] `RemoteNodeClient` — transporte HTTP CORE → SERVER (`/health`, `/tools`, `/tools/execute`), erros padronizados.
- [x] `remote_server_tool` — proxy controlado: somente tools SHARED, `confirmed=False`, LOCAL_ONLY sempre bloqueado.
- [x] `NodePresenceManager` — auto-registro autenticado (`POST /api/devices/`) + heartbeat (`POST /api/devices/heartbeat`) a cada 30s (configurável via `JARVIS_SERVER_HEARTBEAT_INTERVAL`); ambos exigem Bearer compartilhado + `X-Device-Token` individual.
- [x] SERVER offline não impede o funcionamento local do Core (Ollama + tools locais); retry no próximo ciclo, sem retry agressivo.
- [x] IP/porta anunciados somente via `JARVIS_NODE_ADVERTISE_IP` / `JARVIS_NODE_ADVERTISE_PORT` (nenhum endpoint de entrada inventado).
- [x] Task Bridge (`DistributedTaskClient` + 7 métodos no `RemoteNodeClient`): Core cria/consulta/atualiza/completa/falha/cancela/pausa/retoma tasks persistidas no SERVER (`device_id="jarvis-core"`). `PATCH error` traduzido para o histórico `errors` (sem coluna nova, sem schema change). Lifecycle apenas — sem worker/scheduler/queue.
- [x] Google AI Studio (Gemini) como fallback cloud reutilizando `ExternalProvider` (`JARVIS_GOOGLE_*`, slot `google` priority 7, `local=False`); Ollama segue primário (10), mock por último (1). Cloud só enxerga tools SHARED.
- [x] Retry com backoff no `ExternalProvider.generate()` (3 tentativas, ~1s/~2s) para 408/429/500/502/503/504; 4xx permanentes nunca retentam; streaming inalterado.
- [x] Fluxo de confirmação corrigido: aprovação consumida é propagada (`operator_direct`) e falha de tool aprovada nunca é relatada como `"Action completed."`.

---

### ✅ Fase 11: Streaming de Respostas (Concluída)
- [x] `Orchestrator.stream_message()` emite eventos estruturados (`start`, `thinking`, `text_delta`, `tool_call`, `tool_result`, `waiting_confirmation`, `error`, `done`) via `POST /api/chat/stream`.
- [x] SSE `text/event-stream`.
- [x] Tool calls em streaming são acumulados por `call_id` e só executados após fechamento válido.
- [x] Fallback de provider em streaming é honesto: falha antes de qualquer saída pode tentar próximo provider; falha após emissão não mistura providers.
- [x] Exceções reais de transporte/stream não são convertidas em falso `stop`.
- [x] Persistência e gates de PolicyEngine/ToolExecutor/ConfirmationManager permanecem compartilhados com `/api/chat/send`.
- [x] 377 testes coletados na entrega da Fase 11, 375 passando, 2 skips.

---

### ✅ Fase 12: Central Server & Central State Authority (Concluída)

SERVER = control plane / source of truth. CORE = compute plane (Orchestrator, LLM, tools locais).

- [x] `CentralStateClient` (`core/network/central_state_client.py`) sobre `RemoteNodeClient`: conversas, memória e confirmações via HTTP, erros explícitos (`CentralStateError`), nada inventado.
- [x] Flags `JARVIS_CENTRAL_STATE_ENABLED` (default off, modo local preservado) e `JARVIS_CENTRAL_STATE_REQUIRED` (falha explícita, sem fallback silencioso).
- [x] Conversas centrais: `POST/GET /api/conversations/`, `GET /{id}`, `GET/POST /{id}/messages` sobre o schema existente; `ConversationManager` aceita backend central.
- [x] Memória central: `CentralMemoryProvider` com a mesma interface de `BaseMemoryProvider`; `search_memory` usa o backend do runtime. Sem vetores/embeddings nesta fase.
- [x] Confirmações centrais: tabela `confirmations` + `/api/confirmations/*` com consume atômico, single-use, session binding, expiry e `remaining_calls`.
- [x] Gateway: em `node_role=SERVER`, `POST /api/chat/send|stream` encaminha a CORE elegível; sem CORE → HTTP 503 explícito, sem mock e sem resposta inventada.
- [x] Compute interno: `POST /internal/chat/send|stream` com node auth, recusado em role SERVER, reutilizando o Orchestrator.
- [x] Seleção de CORE via presença no `DeviceRegistry` + descriptor confiável (`JARVIS_TRUSTED_DEVICES`); endpoint não vem do SQLite.
- [x] Gemini via SERVER: chave somente no SERVER; relay autenticado; CORE nunca recebe ou armazena a chave Gemini.
- [x] Falhas centrais são explícitas quando `CENTRAL_STATE_REQUIRED=true`.
- [x] Arquitetura preparada para futuro acesso externo seguro sem exposição pública.
- [x] 440 testes coletados, 438 passando, 0 falhas, 2 skips; `compileall` e `diff --check` limpos.

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

#### ⚠️ Planned extensions — Temporal, Vault, Resurrection (futuro, A/H/I)
- [ ] Modelo e persistência de compromissos temporais e intenções condicionais (`temporal_commitments`: gatilho tempo|evento|condições, ação, autorização, expiração) sobre o padrão central existente; sem ticker próprio.
- [ ] Avaliação de condições determinística sobre estado HA/relógio (nunca julgamento do LLM no disparo); execução e expiração via PolicyEngine/ConfirmationManager existentes.
- [ ] Cápsulas cognitivas de contexto (conversa+goals+tasks via Central State); restore sempre como checklist reaplicado com confirmações, nunca injeção de estado.

### ✅ Fase 13: Acesso Externo Seguro
- [x] Permitir uso do JARVIS fora de casa através de **rede privada/VPN**.
- [x] SERVER permanece como único gateway da arquitetura.
- [x] Não expor diretamente o CORE ou ferramentas sensíveis à internet pública.
- [x] Autenticação, autorização e mínimo privilégio para clientes externos.
- [x] Reconexão e disponibilidade quando a conexão externa cair.
- [x] Observabilidade do acesso remoto sem criar dependência de exposição pública.
- [x] Não implementar até a Fase 12 estar validada localmente.

### ✅ Fase 15: Integração Home Assistant (Concluída)
- [x] Home Assistant como backbone de automação doméstica (`core/home_assistant/`, token somente no SERVER).
- [x] Tools SHARED via remote bridge: `home_assistant_get_state(s)` (GREEN), `home_assistant_call_service` (YELLOW), `home_assistant_wake_on_lan` (GREEN); registradas só com role SERVER + HA habilitado.
- [x] Wake-on-LAN para acordar o CORE quando necessário (`wake_on_lan.send_magic_packet`).
- [x] Controle de dispositivos e cenas (scenes/scripts/automations via `call_service`, sem scheduler próprio).
- [x] SERVER continua leve; processamento pesado permanece no CORE.
- [x] Integração respeita o mesmo modelo central de identidade, estado e autorização (PolicyEngine/ConfirmationManager inalterados).
- [x] Documentação (`docs/HOME_ASSISTANT.md`) e script de diagnóstico (`scripts/check_home_assistant.py`).
- [x] Scheduler e automações via Home Assistant (acionamento por `call_service`; sem scheduler próprio em Python).
- [x] Validação operacional: Docker `homeassistant-test` (imagem 2026.6.4, restart `unless-stopped`, persistente após restart), `scripts/check_home_assistant.py` (health/auth/20 entities), Google Home controlando o helper `JARVIS Teste` por voz via Tailscale Funnel (405 em GET esperado).

#### ⚠️ Planned extension — Energy-Aware Compute, leitura (futuro, G)
- [ ] Convenção de leitura de sensores de energia (solar/tarifa/bateria) via tools HA existentes + cálculo puro de política; sem scheduler implícito (adiamento real aguarda Phase 26).

#### ✅ Fase 15.2: Context Architecture (Concluída)
- [x] Orçamento de contexto por provider/modelo (`core/context/budget.py`).
- [x] Seleção determinística de ferramentas (`core/context/tool_selector.py`).
- [x] Compactação determinística de histórico (`core/context/compaction.py`, `conversation_summaries`).
- [x] Rebuild do contexto antes de cada chamada LLM, incluindo streaming.
- [x] `max_tokens` derivado do profile do provider; regressão do qwen3.5:4b corrigida.


---

## Fases Futuras

## 📞Fase 14: Telefonia (intencionalmente pulada — backlog futuro, nada implementado)

> Backlog preservado do planejamento anterior; fora da numeração ativa (que pula a Fase 14 e continua na Fase 15), em espera deliberada, nada implementado ou concluído.
- [ ] Integrar um **número de telefone ao J.A.R.V.I.S.**, criando uma identidade telefônica própria para o agente.
- [ ] Permitir que o J.A.R.V.I.S. **realize chamadas telefônicas de saída** a partir de instruções do usuário.
- [ ] Permitir que o J.A.R.V.I.S. **atenda chamadas recebidas** automaticamente.
- [ ] Permitir que o J.A.R.V.I.S. converse em tempo real com a pessoa durante a ligação.
- [ ] Implementar o pipeline completo de chamada: **chamada → áudio/STT → Orchestrator → LLM/Tools → TTS → áudio**.
- [ ] Usar o mesmo `Orchestrator`, memória, Goals, Tasks, contexto e sistema de segurança do J.A.R.V.I.S.
- [ ] Identificar o número/contato que está ligando e associá-lo à identidade correspondente quando possível.
- [ ] Permitir que o J.A.R.V.I.S. consulte informações e execute ações autorizadas durante uma ligação.
- [ ] Permitir que o J.A.R.V.I.S. **faça ligações para empresas, serviços, pessoas ou contatos** de acordo com instruções explícitas do usuário.
- [ ] Permitir definir um **objetivo de chamada**, como obter informação, confirmar disponibilidade, solicitar orçamento, acompanhar uma solicitação ou transmitir uma mensagem.
- [ ] Permitir que o J.A.R.V.I.S. registre o resultado da chamada no estado central do SERVER.
- [ ] Registrar transcrição, resumo, resultado, duração e ações realizadas de forma controlada.
- [ ] Permitir que o J.A.R.V.I.S. **solicite ajuda ao usuário durante uma chamada** quando não conseguir concluir a tarefa sozinho.
- [ ] Permitir transferência ou encaminhamento da chamada para o usuário quando necessário.
- [ ] Permitir que o J.A.R.V.I.S. reconheça quando uma chamada exige intervenção humana.
- [ ] Implementar **allowlist, autenticação e identificação de chamadas** para evitar que números não autorizados controlem o sistema.
- [ ] Aplicar `PolicyEngine`, `ConfirmationManager` e demais controles de segurança também às ações iniciadas através de chamadas.
- [ ] Exigir confirmação apropriada para ações sensíveis, financeiras, destrutivas ou que possam comprometer o usuário.
- [ ] Separar claramente **comunicação telefônica** de **autorização para executar ações**.
- [ ] Implementar reconexão, tratamento de falhas de áudio, timeout e recuperação de chamadas.
- [ ] Evitar dependência rígida de um único provedor de telefonia.
- [ ] Priorizar integrações e APIs oficiais de telefonia quando disponíveis.
- [ ] Preparar a arquitetura para futuramente suportar **SMS, voicemail e outros canais de comunicação**.
- [ ] Manter o SERVER como autoridade central e o CORE como camada de processamento.
- [ ] O canal telefônico deve ser apenas mais uma interface do mesmo J.A.R.V.I.S., sem criar uma inteligência paralela.


### 🎙️ Fase 16: Pipeline de Voz Local (Próxima)
- [ ] Wake Word.
- [ ] VAD (detecção de atividade de voz).
- [ ] STT local, inicialmente com Whisper ou alternativa equivalente.
- [ ] TTS local, inicialmente com Piper ou alternativa equivalente.
- [ ] Fluxo completo: Wake Word → VAD → STT → Orchestrator → Tool/LLM → TTS.
- [ ] Voz deve utilizar o mesmo JARVIS central, memória, Goals e segurança.
- [ ] Não criar uma segunda inteligência paralela.

#### ⚠️ Planned extensions usando voz (futuro)
- [ ] Entrega falada de compromissos/notificações proativas quando existirem (A4, J3); voz como perna de entrega, sem lógica própria de agendamento.

### 📱 Fase 17: Android & Tablet Dashboard
- [ ] Priorizar Home Assistant Companion e/ou ADB para integração Android.
- [ ] Telemetria, notificações, câmera, microfone e sensores.
- [ ] Comunicação do S20 com o SERVER central.
- [ ] Painel leve para tablet.
- [ ] Avaliar Termux/Termux:API quando um agente local Android for realmente necessário.
- [ ] Ações sensíveis no Android continuam passando pelo modelo de segurança do JARVIS.
- [ ] O canal telefônico deve tratar identidade, autorização, logs e limites de uso antes de permitir ações reais.

#### ⚠️ Planned extensions usando mobile (futuro)
- [ ] Entrega push real e presença móvel para proatividade (A4) e atenção (J2) quando a infraestrutura existir; perna mobile de ressurreição de contexto (I) com os mesmos limites de serialização.

### 👁️ Fase 18: Visão Computacional
- [ ] Captura de tela.
- [ ] OCR quando necessário.
- [ ] Análise visual local.
- [ ] Integração com o contexto do Orchestrator.
- [ ] Separar percepção visual de planejamento e execução.
- [ ] A percepção visual nunca deve conceder autorização automaticamente.
- [ ] Preparar a base necessária para Computer Use da Fase 21.

### 🧠 Fase 19: Memória Vetorial & Busca Semântica
- [ ] Adicionar embeddings locais e busca semântica.
- [ ] Integrar a busca semântica à **memória central já existente**.
- [ ] SERVER continua sendo a autoridade do estado persistente.
- [ ] Avaliar ChromaDB ou alternativas antes de adicionar dependências.
- [ ] Evitar duplicação de memória entre SERVER e CORE.
- [ ] SQLite continua como camada fundamental de estado e auditoria.
- [ ] A memória vetorial deve resolver um problema real de recuperação contextual, e não apenas aumentar complexidade.
- [ ] Definir política de retenção, indexação, atualização e exclusão.
- [ ] Recuperação semântica deve respeitar permissões e isolamento de dados.

### 🤖 Fase 20: Autonomia Progressiva & Goal-Driven Intelligence
- [ ] Evoluir o fluxo **Goal → Plan → Steps → Execution → Observation → Evaluation → Replanning**.
- [ ] Integrar de forma realmente operacional `GoalEngine`, `Planner` e `Orchestrator`.
- [ ] Substituir o replanning puramente hardcoded por decisões orientadas por contexto/LLM quando houver segurança para isso.
- [ ] Permitir estratégias como retry, ferramenta alternativa, decomposição, subgoal, mudança de abordagem e solicitação de ajuda.
- [ ] Evitar parada artificial após poucas tentativas quando ainda houver estratégias seguras disponíveis.
- [ ] Persistir progresso, tentativas, decisões, erros e motivos.
- [ ] Permitir retomada de Goals longos após interrupções.
- [ ] Trabalhar com orçamento de tokens, tempo, ferramentas e limites de execução.
- [ ] Supervisão humana para decisões críticas.

#### ⚠️ Planned extensions supervisionadas (futuro)
- [ ] Restore lógico de contexto/cápsulas (C3) e execução supervisionada de compromissos/intenções (A5, H) somente com confirmação e validação por etapa; nunca autonomia irrestrita.
- [ ] Validar cada etapa antes de permitir que a próxima ação material seja executada.
- [ ] Não confundir autonomia com ausência de controle do usuário.
- [ ] Evoluir o `IntelligenceRouter` para diferenciar necessidades de **thinking/reasoning** e **action/execution**.
- [ ] Avaliar uma arquitetura com modelo maior para planejamento/raciocínio e modelo menor para ações rotineiras, por exemplo Qwen 3.5 9B e Qwen 3.5 4B.
- [ ] O uso de 9B/4B é uma estratégia de referência e não um acoplamento rígido da arquitetura.
- [ ] O router deve decidir pelo tipo e necessidade da tarefa, não apenas pelo nome do modelo.
- [ ] Manter fallback entre modelos/providers sem inventar estado quando um provider falhar.
- [ ] Metas de longa duração devem continuar usando o mesmo estado central do SERVER.

### 🖱️ Fase 21: Computer Use Seguro
- [ ] Captura de tela local.
- [ ] Controle de mouse e teclado como fallback quando não houver API.
- [ ] OCR/visão para compreender a interface.
- [ ] Separar percepção, planejamento e execução.
- [ ] Rate limiting/throttling para ações repetitivas.
- [ ] Validação do contexto antes de executar ações.
- [ ] Classificação de cada ação pelo `PolicyEngine`.
- [ ] Ações potencialmente destrutivas exigem confirmação apropriada.
- [ ] Ferramentas de Computer Use devem preferir APIs e controles nativos antes de mouse/teclado.
- [ ] Usar camadas de segurança para evitar cliques ou comandos fora do contexto esperado.
- [ ] Evitar que screenshot, OCR ou visão sejam tratados como autorização.
- [ ] Projetar compatibilidade com Windows Agent e com a futura visão multimodal.

### 🧬 Fase 22: Self-Editing & Self-Evolution Seguro
- [ ] JARVIS pode propor alterações no próprio código.
- [ ] Sempre trabalhar em branch isolada.
- [ ] Sandbox de edição e execução.
- [ ] Testes completos obrigatórios antes de propor integração.
- [ ] Rollback automático em falha.
- [ ] Nunca permitir autoedição irrestrita de segurança, credenciais ou mecanismos críticos.
- [ ] Alterações em componentes sensíveis devem ser explicitamente bloqueadas ou exigir supervisão adicional.
- [ ] Commit/PR para revisão humana antes de alterar a linha principal.
- [ ] Registrar arquivos alterados, testes executados, resultados e motivo da alteração.
- [ ] Permitir evolução incremental, nunca substituir o sistema inteiro em uma única operação.

#### ⚠️ Planned extension (futuro)
- [ ] Restore privilegiado/destrutivo (C4) como tool RED com confirmação explícita do operador e auditoria completa; sem ele, snapshots permanecem somente-observação.
- [ ] Self-editing deve usar as mesmas políticas de segurança e confirmação do restante do JARVIS.

### 📊 Fase 23: Observabilidade, Benchmarks & Eficiência
- [ ] Métricas de latência, tokens, falhas, retries e custo.
- [ ] Saúde de providers e nós.
- [ ] Rastreamento de tarefas e Goals longos.
- [ ] Benchmarks reproduzíveis de execução, planejamento, ferramentas e recuperação.
- [ ] Medir qualidade de routing, replanning e memória antes de mudar arquitetura.
- [ ] Otimização de roteamento entre modelos e nós.
- [ ] Identificar gargalos antes de adicionar infraestrutura pesada.
- [ ] OpenTelemetry ou solução equivalente somente quando houver necessidade real.
- [ ] Incluir testes de regressão de streaming, gateway e comunicação distribuída.
- [ ] A observabilidade deve preservar privacidade e nunca registrar secrets.

#### ⚠️ Planned extensions (futuro)
- [ ] Snapshots lógicos de estado + comparação determinística (C1/C2, somente leitura/GREEN).
- [ ] Histórico de saúde de hardware e thresholds determinísticos (E1–E3, sem estimar vida útil, sem ação automática).
- [ ] Crescer o volume de auditoria que fundamente futuro posture de segurança (F depende destes dados).

### 🧩 Fase 24: Plugin System & Extensibilidade
- [ ] Sistema de extensões/plugins com contratos claros.
- [ ] Descoberta e registro controlados.
- [ ] Permissões por plugin.
- [ ] Isolamento de plugins não confiáveis.
- [ ] Compatibilidade com ferramentas locais, remotas e futuras integrações.
- [ ] Plugins devem declarar capacidades e requisitos de forma explícita.
- [ ] Nenhum plugin deve contornar `PolicyEngine`, `ToolVisibility` ou autenticação.
- [ ] Plugins devem possuir ciclo de vida controlado e possibilidade de desativação.

### 🔭 Fase 25: Multi-Modalidade Integrada
- [ ] Unificar texto, voz, visão e interfaces externas em um mesmo contexto de sessão.
- [ ] Compartilhar memória, objetivos e estado entre modalidades.
- [ ] Manter uma única autoridade de estado no SERVER.
- [ ] Usar o CORE para processamento pesado multimodal.
- [ ] Preservar os mesmos limites de segurança independentemente da interface.
- [ ] Permitir transição natural entre texto, voz, imagem, tela e dispositivos.
- [ ] Manter identidade e contexto consistentes em todas as modalidades.

---

### 🗓️ Fase 26: Scheduler Foundation
- [ ] Criar uma fundação de scheduler persistente para execução futura de tarefas e compromissos temporais.
- [ ] Suportar avaliação/execução de eventos temporais sem depender de polling ad hoc espalhado pelo código.
- [ ] Persistir compromissos, agendamentos, estado de execução, retry e expiração.
- [ ] Preparar a infraestrutura para compromissos temporais, notificações proativas, deferral de tarefas e execução supervisionada.
- [ ] Integrar com o estado central do SERVER.
- [ ] Preservar PolicyEngine, ConfirmationManager e os limites existentes de autorização.
- [ ] Não criar autonomia irrestrita.
- [ ] Não introduzir filas/workers distribuídos ou infraestrutura pesada sem necessidade comprovada.
- [ ] Preparar a base para Temporal Context Bridge, Energy-Aware Compute, Conditional Intention Vault e Attention Budget Guard.
- [ ] Permitir que o IntelligenceRouter futuramente utilize telemetria real para decisões de roteamento.
- [ ] Manter execução material sujeita às mesmas políticas de segurança do restante do JARVIS.

### 🔎 Fase 27: Evidence & Verification Service
- [ ] Criar uma camada dedicada para coleta e comparação de evidências.
- [ ] Permitir verificação cruzada de informações usando múltiplas fontes independentes quando apropriado.
- [ ] Diferenciar evidência, memória, inferência e resposta gerada.
- [ ] Detectar e preservar conflitos entre fontes em vez de ocultá-los.
- [ ] Integrar com web search, memória central e outras fontes existentes sem duplicar suas responsabilidades.
- [ ] Evitar votação ingênua entre respostas de LLM.
- [ ] Definir critérios determinísticos de confiabilidade/peso das fontes quando possível.
- [ ] Expor ao Orchestrator evidências e conflitos de forma estruturada.
- [ ] Não transformar verificação de evidência em mecanismo de autorização.
- [ ] Preservar PolicyEngine e ConfirmationManager como autoridade de segurança.
- [ ] Preparar a base para Reality Anchor e futuras funções de comparação/verificação de estado.

---

## Considerações Técnicas Transversais

- [ ] Alinhar a versão mínima do Python declarada em `pyproject.toml`, documentação e ambiente de execução antes de declarar suporte oficial.
- [ ] Manter `.env.example` coerente com a arquitetura atual, especialmente com a separação entre SERVER e CORE.
- [ ] A chave Gemini deve permanecer exclusivamente no SERVER.
- [ ] Modelos locais configurados no projeto devem refletir a arquitetura realmente utilizada, sem obrigar a escolha de um modelo específico.
- [ ] Não introduzir banco vetorial, filas ou infraestrutura pesada sem necessidade comprovada.
- [ ] Toda evolução deve preservar as garantias de segurança das Fases 8 e 10.
- [ ] Toda mudança importante deve incluir testes, documentação e validação.
- [ ] O sistema nunca deve mascarar falhas de provider, rede, memória, execução ou estado.
- [ ] Capacidades explicitamente fora do escopo imediato (não implementar sem as fundações acima): push mobile real, execução autônoma irrestrita, restore destrutivo sem confirmação, migração live de tarefas, estimativa de vida útil de hardware, ML local obrigatório, rebaixamento automático de segurança, scheduler distribuído e qualquer nova fila/broker externo.
- [ ] A combinação arquitetural proposta (hub local-first com scheduler determinístico, PolicyEngine única e estado central) é tratada como hipótese de diferenciação do JARVIS, não como afirmação de inexistência de sistemas semelhantes.
- [ ] O SERVER continua sendo **control plane / source of truth**.
- [ ] O CORE continua sendo **compute plane**.
- [ ] O hardware deve continuar desacoplado do desenho de software.
- [ ] O acesso externo futuro deve ocorrer por rede privada segura, nunca por exposição direta de serviços internos.
- [ ] Autonomia deve aumentar a capacidade de executar objetivos mantendo supervisão e controle humano onde necessário.
### Fase 28 — Auditoria da base e linha de referência confiável

**Prioridade imediata.** Começar por inspeção e testes; não fazer uma refatoração grande nesta fase.

- [ ] Registrar branch, commit, estado da árvore de trabalho e versões do ambiente.
- [ ] Mapear entradas do SERVER/CORE, configuração, autenticação, comunicação, persistência e ciclo de vida.
- [ ] Relacionar alegações do README/roadmap ao código e aos testes.
- [ ] Executar a suíte e registrar testes coletados, passados, falhos, ignorados e erros de coleta.
- [ ] Distinguir defeito de código, teste desatualizado, problema de ambiente e integração ainda não testada.
- [ ] Revisar API, ponte CORE/SERVER, estado central, confirmações, SQLite e falhas de rede.
- [ ] Produzir lista priorizada de riscos com evidências e arquivos envolvidos.
- [ ] Escolher uma primeira correção pequena, com critérios de aceitação, testes e rollback.

**Concluída quando:** existe uma linha de base reproduzível, falhas estão categorizadas e a primeira correção pode ser feita com risco controlado.

### Fase 29 — Qualidade contínua e regressão

- [ ] Consolidar comandos reproduzíveis de testes e validações.
- [ ] Configurar CI para verificações essenciais.
- [ ] Isolar banco e estado nos testes.
- [ ] Cobrir contratos, autenticação, confirmações, visibilidade de ferramentas e falhas.
- [ ] Diferenciar mocks de integração simulada e validação operacional real.
- [ ] Cobrir streaming, desconexão, timeouts e providers indisponíveis.
- [ ] Manter README, roadmap, guia de deploy e contagens consistentes com resultados atuais.

**Concluída quando:** a validação automatizada é repetível e a documentação não apresenta contagens sem evidência.

### Fase 30 — Segurança de produção e governança de permissões

- [ ] Rejeitar configurações de produção inseguras e chaves padrão.
- [ ] Validar debug, bind de rede, CORS, autenticação e logging por ambiente.
- [ ] Implementar limites de taxa, payload e concorrência quando necessários.
- [ ] Definir expiração e rotação de credenciais.
- [ ] Separar autenticação de nó da autorização por ação.
- [ ] Aplicar mínimo privilégio por usuário, dispositivo, agente, plugin e ferramenta.
- [ ] Testar SSRF, redirects, traversal, prompt injection e reuso indevido de confirmações.
- [ ] Documentar implantação segura por VPN/rede privada.
- [ ] Versionar mudanças e manter rollback.

**Concluída quando:** o modo de produção falha com segurança diante de configurações inválidas e os limites de autorização são cobertos por testes negativos.

### Fase 31 — Backups e recuperação de desastres

- [ ] Classificar dados essenciais, caches e índices reconstruíveis.
- [ ] Criar backups consistentes de SQLite.
- [ ] Manter cópias históricas em outro dispositivo/local quando possível.
- [ ] Proteger backups contra acesso indevido e ransomware.
- [ ] Verificar integridade e executar restauração em ambiente isolado.
- [ ] Documentar reconstrução do SERVER e retorno seguro do CORE.
- [ ] Definir objetivos realistas de perda de dados e tempo de recuperação.
- [ ] Testar corrupção, backup incompleto, disco cheio e incompatibilidade de schema.
- [ ] Exigir autorização para restaurações que sobrescrevam estado.

**Concluída quando:** um backup é localizado, verificado e restaurado de forma reproduzível. Criar backup sem testar restauração não basta.

### Fase 32 — Orquestração de recursos distribuídos

- [ ] Definir contrato de capacidades do nó: papel, CPU, RAM, aceleradores, disco, carga e atualização da telemetria.
- [ ] Tratar heartbeat ausente e métricas antigas como capacidade desconhecida.
- [ ] Preservar a responsividade do SERVER.
- [ ] Roteiar tarefas por requisitos de memória, modelo, latência, privacidade e disponibilidade.
- [ ] Diferenciar paralelismo de tarefas do paralelismo interno de um modelo.
- [ ] Começar pelo despacho de novas tarefas; não migrar tarefas em execução sem checkpoint e retomada testados.
- [ ] Reutilizar o IntelligenceRouter existente.
- [ ] Preparar perfil All-in-One sem duplicar lógica.
- [ ] Testar nós lentos, desconectados e sem recursos suficientes.

**Concluída quando:** a seleção de nó é explicável, falhas não perdem tarefas silenciosamente e os serviços essenciais do SERVER permanecem disponíveis.

### Fase 33 — Memória de longo prazo e proveniência

- [ ] Diferenciar memória episódica, histórica, semântica, temporária, preferências e intenções.
- [ ] Registrar origem, instante, última confirmação, confiança e retenção quando aplicável.
- [ ] Diferenciar fatos, declarações, inferências, hipóteses, previsões e conteúdo não literal.
- [ ] Tratar conflitos e dados desatualizados sem apagar o histórico silenciosamente.
- [ ] Fazer compactação e arquivamento reversíveis.
- [ ] Usar busca semântica apenas quando necessária; manter índices reconstruíveis.
- [ ] Respeitar permissões e isolamento entre sessões.
- [ ] Definir exportação, correção, exclusão e expiração.

**Concluída quando:** a recuperação mostra proveniência e atualidade, respeita permissões e possui retenção/exclusão testadas.

### Fase 34 — Estado do mundo e gestão de incerteza

- [ ] Integrar evidências a observações reais de tools, APIs, Home Assistant, nós e memória.
- [ ] Registrar origem, instante, atualidade, contexto e conflitos de afirmações.
- [ ] Diferenciar observado, inferido, previsto, planejado, desconhecido e desatualizado.
- [ ] Consultar novamente dados mutáveis quando necessário.
- [ ] Resolver conflitos por critérios explícitos.
- [ ] Não inventar localização, estado de dispositivo ou relações espaciais.
- [ ] Perguntar ao usuário quando a incerteza restante mudar materialmente a decisão.
- [ ] Nunca usar confiança do modelo como autorização.

**Concluída quando:** o sistema informa o que sabe e de onde veio, detecta dados obsoletos e não transforma inferências em permissões.

### Fase 35 — Proatividade e aprendizado seguro de rotinas

- [ ] Definir canais, horários silenciosos, frequência e limites de notificação.
- [ ] Separar sugestão, notificação e execução.
- [ ] Aprender possíveis rotinas com evidências suficientes, sem tratar padrões como ordens confirmadas.
- [ ] Começar com sugestões; automação exige opt-in e limiar verificável.
- [ ] Automatizar apenas ações de baixo risco explicitamente autorizadas.
- [ ] Usar PolicyEngine/ConfirmationManager para ações materiais.
- [ ] Reutilizar scheduler e Home Assistant, evitando timers duplicados.
- [ ] Prevenir loops, duplicações e excesso de notificações.
- [ ] Permitir pausar, corrigir e revogar rotinas.

**Concluída quando:** a proatividade é controlável, pouco intrusiva e não executa ações além das permissões concedidas.

### Fase 36 — Autocorreção e evolução controlada

- [ ] Criar supervisão de saúde com sinais independentes e timeouts.
- [ ] Definir retry, backoff, circuit breaker e limites de tentativas.
- [ ] Distinguir reinício seguro de alterações de segurança, credenciais ou dados.
- [ ] Gerar diagnósticos baseados em evidências.
- [ ] Usar branch isolada, sandbox, testes e revisão para patches.
- [ ] Validar antes de implantar e reverter diante de falha objetiva.
- [ ] Exigir aprovação para mudanças sensíveis ou destrutivas.
- [ ] Proibir que o modelo enfraqueça políticas, remova logs ou aumente suas permissões.
- [ ] Auditar diagnóstico, patch, autorização, implantação e rollback.

**Concluída quando:** recuperação e rollback são reproduzíveis e a autocorreção não pode reduzir a segurança.

### Fase 37 — Bootstrap, instalação e perfis de distribuição

- [ ] Definir contratos comuns para SERVER, AI NODE/CORE, APP e All-in-One.
- [ ] Detectar sistema operacional, CPU, RAM, disco, aceleradores e dependências.
- [ ] Criar instalação guiada com progresso, diagnóstico e verificação de saúde.
- [ ] Usar Docker no SERVER quando fizer sentido, sem exigir em plataformas incompatíveis.
- [ ] Validar suporte real a Windows, Linux e macOS antes de declará-lo.
- [ ] Separar dados, configuração, logs, caches e secrets.
- [ ] Descobrir dispositivos sem confiar neles automaticamente.
- [ ] Incluir atualização, migração, desinstalação e rollback sem apagar dados silenciosamente.
- [ ] Permitir All-in-One sem duplicar a arquitetura.
- [ ] Não abrir portas públicas por padrão.

**Concluída quando:** instalação e atualização são repetíveis nos ambientes testados e falhas podem ser recuperadas com segurança.

### Fase 38 — Identidade, sessões e continuidade entre dispositivos

- [ ] Manter o celular como interface de conversa, notificações e aprovações; execução principal fica no SERVER/CORE.
- [ ] Associar estado central a usuário, sessão, dispositivo e pedido.
- [ ] Mostrar ação, alvo, risco e efeito esperado em cada aprovação.
- [ ] Usar APIs biométricas do sistema operacional; não armazenar dados biométricos brutos.
- [ ] Definir expiração de sessão, reautenticação e confirmação reforçada para ações sensíveis.
- [ ] Permitir revogar dispositivos perdidos.
- [ ] Evitar conteúdo sensível em notificações de tela bloqueada.
- [ ] Não tratar biometria ou posse do telefone como autorização irrestrita.
- [ ] Preservar continuidade sem misturar sessões entre usuários.

## Fases Complementares — Evolução do Jarvis como Agente Completo

As fases a seguir complementam o roadmap existente para aproximar o J.A.R.V.I.S. das capacidades de produtividade, integração e experiência de uso de agentes modernos, incluindo o Hermes Agent.

Essas fases não substituem as anteriores. Elas ampliam as capacidades do produto e devem reutilizar a arquitetura, os contratos, o estado central, o sistema de ferramentas e os mecanismos de segurança já estabelecidos.

Toda implementação deverá começar pela análise do estado real do repositório. Antes de criar novos componentes, verificar o que já existe, o que funciona, o que está incompleto e o que pode ser reutilizado.

### Fase 39 — Sistema de Skills e Aprendizado Procedimental

**Objetivo:** permitir que o Jarvis transforme procedimentos úteis em habilidades reutilizáveis, carregadas sob demanda, para realizar tarefas recorrentes com mais eficiência, consistência e capacidade de recuperação.

O sistema de skills deverá complementar o sistema de plugins, os agentes, a memória, o Planner e o Orchestrator. Uma skill representa um procedimento reutilizável; um plugin fornece capacidades ou ferramentas; a memória preserva informações relevantes. Esses conceitos não devem ser confundidos nem implementados como sistemas duplicados.

#### Requisitos funcionais

- [ ] Criar um formato padronizado para skills, com identificador, nome, descrição, versão, instruções, pré-requisitos, ferramentas necessárias e critérios de sucesso.
- [ ] Permitir descobrir, listar, consultar, instalar, ativar, desativar, atualizar e remover skills.
- [ ] Carregar instruções de uma skill somente quando forem relevantes para a tarefa, evitando consumir contexto desnecessariamente.
- [ ] Permitir que uma skill seja criada a partir de um procedimento definido pelo usuário ou proposta pelo Jarvis após tarefas relevantes e recorrentes.
- [ ] Separar instruções procedimentais de código executável e de permissões de acesso.
- [ ] Identificar as ferramentas, os serviços e os recursos exigidos por cada skill.
- [ ] Validar pré-requisitos antes da execução e verificar resultados após cada etapa relevante.
- [ ] Permitir composição de skills em planos maiores, mantendo dependências, limites e critérios de conclusão.
- [ ] Integrar skills ao Planner, GoalEngine, Orchestrator, ToolRegistry, memória central e sistema de tarefas existente.
- [ ] Versionar habilidades, registrar sua origem e preservar histórico de alterações.
- [ ] Permitir comparar versões, reverter atualizações e desativar habilidades problemáticas.
- [ ] Registrar execuções, resultados, falhas e métricas de sucesso sem armazenar segredos indevidamente.
- [ ] Permitir exportar e importar skills em formato documentado e compatível com ferramentas externas quando apropriado.
- [ ] Avaliar compatibilidade com o padrão aberto Agent Skills antes de criar um formato proprietário desnecessário.

#### Aprendizado e evolução de skills

- [ ] Identificar procedimentos que se repetem ou que podem ser transformados em fluxos reutilizáveis.
- [ ] Após tarefas relevantes, avaliar o resultado, identificar erros recorrentes e registrar lições úteis.
- [ ] Permitir que o Jarvis proponha novas skills ou melhorias nas existentes.
- [ ] Validar alterações em ambiente apropriado antes de disponibilizá-las.
- [ ] Comparar resultados anteriores e posteriores para verificar se uma melhoria realmente aumentou a confiabilidade.
- [ ] Evitar aprender automaticamente instruções maliciosas, ocasionais, incorretas ou incompatíveis com as políticas do sistema.
- [ ] Não considerar uma execução bem-sucedida isolada como prova suficiente de que uma skill está correta.
- [ ] Permitir revisão, aprovação, rejeição e reversão pelo usuário.
- [ ] Garantir que o aprendizado não conceda novas permissões à skill, ao agente ou ao próprio Jarvis.

#### Segurança

- [ ] Toda skill deverá utilizar as permissões e ferramentas explicitamente autorizadas para a sessão e a tarefa.
- [ ] Uma skill não poderá ignorar o PolicyEngine, o ConfirmationManager ou as regras de autenticação.
- [ ] Instruções presentes em arquivos, páginas web e skills de terceiros deverão ser tratadas como conteúdo não confiável até serem validadas.
- [ ] Skills não poderão obter credenciais, dados ou acesso a ferramentas além do escopo autorizado.
- [ ] Alterações de código, execução de comandos perigosos e operações destrutivas deverão seguir os mecanismos de isolamento, aprovação e auditoria existentes.
- [ ] O sistema deverá oferecer meios para identificar a origem de uma skill e avaliar seus requisitos antes da instalação.

**Critérios de conclusão:**

A fase será considerada concluída quando o Jarvis conseguir instalar, selecionar, executar, versionar, validar e reverter skills de forma reproduzível; quando skills forem reutilizáveis entre tarefas compatíveis; e quando todas as execuções permanecerem subordinadas às políticas de segurança existentes.

### Fase 40 — Gateway Multiplataforma de Comunicação

**Objetivo:** permitir que o usuário interaja com o Jarvis por diferentes canais de comunicação, preservando uma identidade, um estado central e uma política de segurança consistentes.

O gateway deverá complementar a API, o aplicativo e a arquitetura de continuidade entre dispositivos. Não deverá criar uma segunda camada de memória, autenticação ou autorização independente do SERVER.

#### Requisitos funcionais

- [ ] Definir uma interface comum para adaptadores de canais de comunicação.
- [ ] Implementar primeiro um canal de mensagens para validação ponta a ponta, escolhendo a plataforma conforme as necessidades e as condições de integração.
- [ ] Preparar a arquitetura para canais adicionais, como Telegram, Discord, WhatsApp ou outros serviços compatíveis, sem exigir que todos sejam implementados na primeira entrega.
- [ ] Encaminhar mensagens recebidas ao fluxo central de sessões, conversas, tarefas e execução.
- [ ] Permitir enviar respostas, notificações, resultados, atualizações de progresso e solicitações de confirmação.
- [ ] Suportar mensagens de texto e, conforme as capacidades de cada plataforma, imagens, arquivos e mensagens de voz.
- [ ] Permitir relacionar uma mensagem recebida a um usuário, canal, dispositivo e sessão autorizados.
- [ ] Preservar o histórico central mesmo quando a conversa mudar de canal, desde que a identidade e as permissões tenham sido verificadas.
- [ ] Evitar a mistura de conversas, sessões ou dados pertencentes a usuários diferentes.
- [ ] Tratar desconexões, limites de API, falhas de entrega, mensagens duplicadas e eventos fora de ordem.
- [ ] Utilizar identificadores de operação e mecanismos de idempotência para evitar executar duas vezes uma ação devido à repetição de mensagens.
- [ ] Permitir consultar o estado de entrega das notificações quando a plataforma disponibilizar essa informação.
- [ ] Permitir desativar, desconectar e revogar o acesso de qualquer canal.
- [ ] Documentar limitações, permissões necessárias, configuração e recuperação de cada integração.

#### Aprovações e segurança

- [ ] Todas as ações recebidas por canais externos deverão utilizar as mesmas políticas de segurança do aplicativo e da API.
- [ ] Mensagens provenientes de um canal não deverão ser consideradas autorizadas apenas por conhecerem um identificador de conversa ou um nome de usuário.
- [ ] Aprovações deverão estar vinculadas à identidade autorizada, à sessão, à ação e ao escopo correspondente.
- [ ] Tokens de confirmação deverão continuar específicos, expiráveis e de uso controlado, sem serem aceitos indiscriminadamente entre canais.
- [ ] Canais externos não poderão conceder permissões administrativas nem alterar as políticas do Jarvis.
- [ ] A execução de ações sensíveis deverá utilizar os mecanismos de confirmação e autorização já existentes.
- [ ] Notificações não deverão expor desnecessariamente informações sensíveis na tela bloqueada ou a destinatários incorretos.
- [ ] Credenciais de integrações deverão ser armazenadas em local apropriado e nunca expostas em mensagens ou logs.
- [ ] As permissões deverão poder ser limitadas por canal, usuário, grupo e tipo de ação, conforme suportado pela integração.

#### Continuidade de sessão

- [ ] Permitir continuar uma conversa por outro canal autorizado sem duplicar o estado central.
- [ ] Manter referências aos objetivos, tarefas e confirmações relacionadas à conversa.
- [ ] Revalidar a identidade quando necessário antes de expor informações ou permitir ações sensíveis.
- [ ] Permitir interromper uma tarefa e consultar seu estado por qualquer interface autorizada.
- [ ] Garantir que uma mensagem enviada por um canal não reinicie nem duplique silenciosamente uma tarefa que já esteja em execução.

**Critérios de conclusão:**

A fase será considerada concluída quando um canal implementado permitir conversar com o Jarvis, iniciar tarefas, acompanhar resultados e receber notificações utilizando o estado central do SERVER. A identidade, as permissões e as confirmações deverão permanecer válidas apenas dentro de seus escopos autorizados.

Novos canais deverão poder ser adicionados por adaptadores independentes, sem duplicar a lógica principal do agente.

### Fase 41 — Automação de Navegador e Web

**Objetivo:** permitir que o Jarvis execute tarefas na web de maneira estruturada, verificável e segura, complementando a pesquisa online e o Computer Use existente.

A automação deverá preferir interfaces estruturadas e APIs quando disponíveis. Mouse, teclado, captura de tela e OCR deverão funcionar como alternativas quando não houver uma interface mais confiável.

#### Requisitos funcionais

- [ ] Definir uma interface de navegador compatível com o sistema de ferramentas do Jarvis.
- [ ] Permitir iniciar, consultar, controlar e encerrar sessões de navegador.
- [ ] Permitir abrir URLs, navegar entre páginas, consultar títulos, identificar elementos, acessar links e inspecionar conteúdo relevante.
- [ ] Permitir interagir com elementos e formulários de maneira estruturada.
- [ ] Suportar múltiplas páginas e abas, mantendo uma identificação clara do contexto ativo.
- [ ] Permitir preencher formulários, selecionar opções e realizar pesquisas em sites.
- [ ] Permitir baixar e enviar arquivos quando a operação estiver autorizada e for compatível com a plataforma.
- [ ] Integrar o estado do navegador ao contexto da tarefa para evitar confundir abas, páginas ou usuários.
- [ ] Permitir utilizar automação visual como complemento para interfaces sem controles estruturados adequados.
- [ ] Verificar o resultado de cada etapa importante, em vez de presumir que um clique ou comando funcionou.
- [ ] Detectar mudanças de página, elementos inexistentes, carregamentos incompletos e sessões expiradas.
- [ ] Permitir interromper, retomar quando seguro e replanejar uma sequência de navegação.
- [ ] Registrar etapas relevantes, resultados, falhas e evidências, respeitando as políticas de privacidade.
- [ ] Integrar a automação ao Planner, Orchestrator, sistema de tarefas e serviço de verificação de evidências.
- [ ] Evitar desenvolver um navegador próprio quando uma solução mantida e compatível puder ser integrada de forma segura.

#### Segurança e isolamento

- [ ] Manter sessões de navegador isoladas conforme o usuário, a tarefa e o nível de confiança.
- [ ] Definir limites de acesso a domínios, arquivos, rede e downloads.
- [ ] Tratar páginas, documentos e instruções encontradas na internet como fontes potencialmente não confiáveis.
- [ ] Impedir que instruções de páginas web alterem as políticas de segurança, concedam permissões ou autorizem ações no sistema operacional.
- [ ] Não disponibilizar automaticamente credenciais pessoais, cookies ou sessões autenticadas a qualquer tarefa.
- [ ] Proteger contra acesso a endereços internos sensíveis, serviços de metadados e recursos não autorizados.
- [ ] Classificar as ações de navegador usando o PolicyEngine.
- [ ] Exigir confirmação apropriada para ações materiais, como publicar conteúdo, enviar comunicações, fazer compras, modificar configurações de conta ou realizar operações irreversíveis.
- [ ] Limitar frequência, concorrência e duração das operações.
- [ ] Permitir encerrar sessões, apagar dados temporários e revogar acessos.
- [ ] Garantir que downloads e arquivos obtidos durante a navegação não sejam executados automaticamente.

#### Integração com Computer Use

- [ ] Reutilizar a separação entre percepção, planejamento e execução estabelecida na Fase 21.
- [ ] Preferir APIs, seletores e controles estruturados antes de mouse e teclado.
- [ ] Quando a interação visual for necessária, verificar o contexto da tela antes de executar cada ação relevante.
- [ ] Tratar OCR e análise visual como evidência de contexto, nunca como autorização.
- [ ] Aplicar as mesmas políticas de segurança independentemente da técnica de automação utilizada.
- [ ] Registrar de forma diferenciada as ações estruturadas e as ações baseadas em coordenadas visuais.

**Critérios de conclusão:**

A fase será considerada concluída quando o Jarvis conseguir executar um fluxo web de várias etapas, verificar os resultados, tratar erros comuns, interromper a tarefa com segurança e registrar evidências suficientes para explicar o que ocorreu.

Os testes deverão incluir páginas alteradas, falhas de rede, sessões expiradas, permissões negadas, conteúdo malicioso e tentativas de ultrapassar os limites de acesso.

---

## Requisitos Complementares para Fases Existentes

Os itens a seguir ampliam as fases já presentes no roadmap. Eles não exigem a criação de sistemas duplicados e deverão ser implementados dentro das fases correspondentes, conforme suas dependências e prioridades.

### Complementos à Fase 24 — Plugin System e Interoperabilidade

- [ ] Avaliar e implementar um cliente MCP para conexão com servidores de ferramentas compatíveis.
- [ ] Suportar os transportes necessários, priorizando servidores locais e conexões remotas seguras.
- [ ] Permitir descobrir, listar, atualizar e desconectar ferramentas fornecidas por servidores MCP.
- [ ] Criar uma interface de configuração e gerenciamento das conexões.
- [ ] Definir autenticação, autorização e armazenamento protegido de credenciais quando aplicáveis.
- [ ] Separar o papel do servidor MCP do papel do cliente MCP.
- [ ] Permitir registrar a origem, as capacidades e os requisitos de cada integração.
- [ ] Definir um catálogo de plugins e integrações aprovadas, com versões, documentação e histórico de atualização.
- [ ] Exigir autorização individual das capacidades materiais, sem conceder acesso irrestrito por instalar um plugin.
- [ ] Garantir que ferramentas descobertas dinamicamente passem pelos mesmos controles de visibilidade e autorização.
- [ ] Permitir desativar e remover integrações sem deixar credenciais ou processos órfãos.
- [ ] Não confiar automaticamente em ferramentas ou servidores MCP apenas porque o protocolo é compatível.

**Critérios adicionais de conclusão:** deve ser possível conectar e desconectar uma integração compatível, descobrir suas ferramentas, controlar seu acesso e executar chamadas autorizadas com auditoria e tratamento de falhas.

### Complementos à Fase 26 — Scheduler Foundation

- [ ] Registrar o histórico de cada execução, incluindo horário, duração, resultado, erros e tentativas.
- [ ] Diferenciar tarefa agendada, execução iniciada, execução concluída, execução falha e entrega de notificação não confirmada.
- [ ] Evitar execução duplicada quando houver reinicialização, repetição de eventos ou indisponibilidade temporária.
- [ ] Implementar políticas de retry, backoff, expiração e limites de tentativas.
- [ ] Recuperar o estado das tarefas após reinicialização sem repetir automaticamente operações materiais que já possam ter sido executadas.
- [ ] Definir claramente fuso horário, recorrência, próxima execução e comportamento durante mudanças de horário.
- [ ] Permitir listar, pausar, retomar, editar, executar agora e remover tarefas.
- [ ] Permitir cancelamento seguro quando a tarefa estiver em execução.
- [ ] Notificar o usuário sobre falhas persistentes e problemas de entrega quando apropriado.
- [ ] Garantir que tarefas recorrentes reutilizem as políticas de autorização e confirmação.
- [ ] Reutilizar o estado central do SERVER e evitar schedulers independentes em cada nó sem necessidade comprovada.

**Critérios adicionais de conclusão:** tarefas deverão manter um histórico verificável, sobreviver a reinicializações dentro das garantias documentadas e distinguir claramente sucesso operacional de entrega não confirmada.

### Complementos à Fase 30 — Segurança e Isolamento Geral de Execução

- [ ] Definir ambientes isolados para executar código gerado, plugins não confiáveis e tarefas que exijam acesso ao sistema operacional.
- [ ] Avaliar containers ou outros mecanismos de isolamento apropriados para os sistemas suportados.
- [ ] Separar as permissões de execução local, execução remota e execução em ambientes isolados.
- [ ] Aplicar limites de CPU, memória, tempo, processos e armazenamento temporário.
- [ ] Controlar o acesso ao sistema de arquivos e à rede dentro do ambiente de execução.
- [ ] Impedir que tarefas não confiáveis recebam automaticamente credenciais, tokens ou variáveis de ambiente sensíveis.
- [ ] Definir o ciclo de vida dos ambientes isolados, incluindo criação, encerramento, limpeza e retenção.
- [ ] Bloquear escape de sandbox como requisito explícito de testes de segurança, dentro dos mecanismos adotados.
- [ ] Registrar origem, permissões, ambiente utilizado, resultados e falhas das execuções.
- [ ] Exigir confirmação ou bloquear ações fora do escopo permitido.
- [ ] Não considerar containers, sandbox ou aprovação de comandos como substitutos da autorização central.
- [ ] Documentar quais tipos de isolamento estão realmente disponíveis em cada plataforma suportada.

**Critérios adicionais de conclusão:** código e tarefas não confiáveis deverão operar com os privilégios mínimos necessários, limites técnicos verificáveis e impossibilidade de acessar automaticamente recursos externos ao escopo autorizado.

### Complementos à Fase 33 — Memória e Pesquisa de Histórico

- [ ] Disponibilizar pesquisa textual em conversas anteriores, além de pesquisa semântica.
- [ ] Recuperar mensagens originais com referência à conversa, data, sessão e contexto relevante.
- [ ] Permitir filtrar resultados por projeto, assunto, período, tarefa ou ferramenta quando houver metadados adequados.
- [ ] Integrar os resultados da pesquisa ao contexto de tarefas atuais sem carregar todo o histórico desnecessariamente.
- [ ] Fazer resumos de memória apontarem para as fontes que os originaram, quando possível.
- [ ] Permitir inspecionar, corrigir, exportar e excluir memórias.
- [ ] Diferenciar exclusão da memória resumida da exclusão do histórico original.
- [ ] Aplicar os mesmos limites de autorização e isolamento a toda pesquisa.
- [ ] Permitir reconstruir o contexto relevante de uma tarefa antiga usando dados persistidos e verificáveis.
- [ ] Manter índices pesquisáveis reconstruíveis a partir dos dados de origem quando apropriado.

**Critérios adicionais de conclusão:** o usuário deverá conseguir localizar uma informação antiga, consultar a fonte original e utilizar o contexto recuperado em uma nova tarefa, sem misturar sessões ou expor dados não autorizados.

### Complementos às Fases 35 e 36 — Ciclo de Aprendizado e Melhoria

- [ ] Integrar avaliação de resultados, memória, skills, métricas e autocorreção em um processo controlado.
- [ ] Após tarefas relevantes, comparar o resultado real com os critérios de sucesso.
- [ ] Registrar causas prováveis de falha, alternativas tentadas e soluções confirmadas.
- [ ] Identificar lições que possam ser reutilizadas sem armazenar dados desnecessários.
- [ ] Permitir que o Jarvis proponha atualizações de skills, procedimentos ou planos de execução.
- [ ] Testar melhorias antes de promovê-las para uso recorrente.
- [ ] Medir os resultados de melhorias em tarefas representativas.
- [ ] Não alterar automaticamente permissões, políticas, credenciais ou mecanismos críticos de segurança.
- [ ] Permitir aprovação, rejeição, revisão e reversão de mudanças.
- [ ] Manter rastreabilidade entre o problema identificado, a mudança proposta, os testes e os resultados posteriores.

**Critérios adicionais de conclusão:** o Jarvis deverá demonstrar um ciclo reproduzível de avaliação e melhoria que aumente a confiabilidade sem reduzir a segurança ou modificar permissões por conta própria.

### Complementos à Fase 37 — Instalação, Configuração e Administração

- [ ] Criar uma interface administrativa para configurar e monitorar os componentes principais do Jarvis.
- [ ] Permitir conectar, desconectar e configurar provedores de IA por um fluxo guiado.
- [ ] Validar credenciais e conectividade antes de habilitar provedores externos.
- [ ] Exibir os modelos disponíveis, capacidades relevantes, limitações e estado de saúde dos provedores.
- [ ] Permitir configurar preferências de roteamento por tipo de tarefa, respeitando as políticas de privacidade.
- [ ] Exibir nós conectados, recursos disponíveis, serviços ativos e tarefas em execução.
- [ ] Disponibilizar gestão de plugins, servidores MCP, skills e canais de comunicação.
- [ ] Disponibilizar histórico de tarefas, aprovações pendentes, erros e diagnósticos.
- [ ] Permitir consultar e gerenciar permissões, sessões e dispositivos autorizados.
- [ ] Disponibilizar ferramentas de backup, validação de integridade e acompanhamento da recuperação.
- [ ] Exibir latência, falhas, consumo de tokens e custos estimados quando esses dados estiverem disponíveis.
- [ ] Garantir que os segredos sejam protegidos e nunca apresentados em logs ou no contexto enviado aos modelos.
- [ ] Permitir executar diagnósticos, verificar dependências e acompanhar atualizações.
- [ ] Manter alternativas por linha de comando para recuperação e administração quando a interface estiver indisponível.
- [ ] Validar a experiência de instalação e administração em cada plataforma declarada como suportada.

**Critérios adicionais de conclusão:** operações rotineiras de configuração, diagnóstico e manutenção deverão ser possíveis por uma interface documentada, sem exigir edição manual de arquivos para cada alteração comum.

### Complementos à Fase 38 — Continuidade de Uso e Controle de Tarefas

- [ ] Permitir consultar e acompanhar tarefas por interfaces autorizadas.
- [ ] Exibir progresso, etapa atual, dependências, erros e confirmações pendentes.
- [ ] Permitir pausar, cancelar e retomar tarefas quando o estado e as operações envolvidas tornarem isso seguro.
- [ ] Garantir que uma interrupção não deixe subprocessos ou ações materiais executando silenciosamente.
- [ ] Permitir enviar novas instruções para tarefas em andamento sem misturar sessões.
- [ ] Exibir ferramentas utilizadas e resultados relevantes de forma compreensível.
- [ ] Permitir consultar evidências associadas ao resultado final.
- [ ] Preservar a continuidade entre canais e dispositivos sem ignorar reautenticação ou requisitos de confirmação.
- [ ] Garantir que a indisponibilidade de uma interface não apague nem invalide o estado central da tarefa.

**Critérios adicionais de conclusão:** o usuário deverá conseguir entender o que o Jarvis está fazendo, interromper operações compatíveis, consultar resultados e recuperar o estado após desconexões ou reinicializações, sem gerar execução duplicada ou perda silenciosa de progresso.

---

## Ordem Recomendada de Implementação das Extensões

As fases complementares deverão respeitar as dependências da arquitetura e não deverão provocar uma reescrita desnecessária do projeto.

1. **Concluir e validar a fundação:** executar a auditoria da Fase 28, estabilizar os testes da Fase 29 e corrigir riscos prioritários.
2. **Fortalecer a operação:** aprimorar segurança, isolamento, scheduler, memória pesquisável, gestão de integrações e experiência administrativa.
3. **Implementar o sistema de skills:** aproveitar ferramentas, agentes, memória, plugins e critérios de validação já existentes.
4. **Implementar o gateway de comunicação:** iniciar com um canal, validar identidade, sessões, tarefas e aprovações e então expandir.
5. **Implementar a automação de navegador:** integrar ferramentas estruturadas, isolamento, permissões e verificação de resultados.
6. **Validar a integração completa:** testar fluxos de ponta a ponta, incluindo falhas, retomada, concorrência, ausência de rede e ações negadas.
7. **Medir resultados reais:** utilizar métricas, benchmarks reproduzíveis e tarefas representativas para decidir quais melhorias adicionais realmente se justificam.

Não é necessário implementar todas as integrações ao mesmo tempo. A arquitetura deverá permitir acrescentá-las de maneira incremental, documentada e testável.

## Critério Geral de Conclusão das Extensões

As novas capacidades não deverão ser declaradas concluídas apenas porque existem classes, endpoints, interfaces ou testes unitários.

Cada capacidade deverá demonstrar um fluxo funcional de ponta a ponta, com estado persistente quando necessário, permissões verificadas, tratamento de falhas, evidências do resultado e documentação atualizada.

Mocks podem validar componentes isolados, mas não substituem a validação operacional de integrações reais.

O Jarvis deverá manter a mesma autoridade central, as mesmas políticas de segurança e o mesmo modelo de auditoria independentemente da quantidade de ferramentas, skills, canais ou nós disponíveis.

**Princípio permanente:** ampliar as capacidades do Jarvis sem duplicar responsabilidades, enfraquecer as políticas de segurança ou transformar funcionalidades ainda não validadas em promessas de funcionamento.
---

**Concluída quando:** cada ação é autorizada no servidor, aprovações são específicas e expiram, e a troca de interface não mistura estado.

## Visão Final — O Jarvis após a conclusão de todas as fases

### 1. Objetivo principal

Ao final de todas as fases, o Jarvis deverá ser um assistente pessoal inteligente, persistente, multimodal, proativo, modular e distribuído, capaz de compreender meus objetivos, utilizar os recursos disponíveis, executar tarefas autorizadas, aprender minhas preferências e me ajudar a administrar atividades digitais e dispositivos conectados.

O Jarvis não deverá ser apenas um chatbot que responde perguntas. Ele deverá funcionar como um sistema integrado capaz de transformar solicitações em planos, planos em ações autorizadas, ações em resultados verificáveis e resultados em conhecimento útil para o futuro.

Seu objetivo será me ajudar a estudar, programar, desenvolver projetos, organizar informações, administrar computadores e serviços, automatizar tarefas e controlar dispositivos compatíveis, sempre respeitando minhas permissões, minha privacidade e minhas decisões.

O Jarvis deverá funcionar como um assistente contínuo, e não como uma ferramenta que esquece tudo a cada conversa.

### 2. Arquitetura integrada e distribuída

O Jarvis deverá funcionar por meio de uma arquitetura modular, na qual cada componente tenha responsabilidades claras.

- **SERVER:** será o centro de controle do sistema, responsável pela API, autenticação, autorização, estado persistente, memória central, gerenciamento dos nós, coordenação de tarefas, confirmações, auditoria e comunicação entre componentes.
- **CORE / AI NODE:** será responsável pelo processamento de inteligência artificial, raciocínio, planejamento, interpretação multimodal e execução dos componentes de IA. Poderá utilizar o computador principal, o servidor ou outros nós disponíveis, conforme os requisitos de cada tarefa.
- **APP:** será a interface principal do usuário, especialmente no celular, permitindo conversar com o Jarvis, receber notificações, acompanhar tarefas, fornecer informações e aprovar ou rejeitar ações.
- **Nós adicionais:** computadores e outros equipamentos autorizados poderão fornecer CPU, memória, aceleradores, armazenamento ou serviços específicos.
- **Integrações e ferramentas:** módulos especializados poderão conectar o Jarvis a sistemas operacionais, arquivos, aplicações, serviços online, APIs, Home Assistant e outros sistemas compatíveis.

Todos esses componentes deverão trabalhar como um único sistema, mesmo quando estiverem em dispositivos diferentes. O usuário não deverá precisar compreender toda a complexidade interna para utilizar o Jarvis.

O SERVER deverá permanecer como autoridade sobre o estado persistente e as permissões. Os demais componentes não poderão se tornar fontes independentes e conflitantes de verdade.

### 3. Conversação natural e capacidades multimodais

O Jarvis deverá permitir uma interação natural por texto e, conforme os módulos estiverem implementados e disponíveis, por voz, imagens e outros tipos de entrada multimodal.

Deverá conseguir:

- Compreender perguntas, solicitações, instruções e objetivos compostos por várias etapas.
- Utilizar o contexto da conversa e as memórias relevantes para evitar perguntas repetitivas.
- Explicar o que está fazendo e apresentar resultados de maneira clara.
- Identificar quando não possui informações suficientes e solicitar esclarecimentos quando isso realmente fizer diferença.
- Reconhecer limitações e distinguir fatos observados de inferências.
- Adaptar o nível de detalhe, o tom e a forma de comunicação às preferências do usuário.
- Interromper, pausar ou replanejar uma tarefa quando receber novas instruções.

A experiência deverá ser fluida: o usuário poderá iniciar uma atividade no computador, continuar pelo celular e consultar posteriormente o histórico sem perder a continuidade, respeitando as permissões e o isolamento das sessões.

### 4. Memória persistente e conhecimento contextual

O Jarvis deverá manter uma memória útil entre conversas e reinicializações. As informações deverão ser organizadas de forma que possam ser consultadas, atualizadas, corrigidas, exportadas ou excluídas.

A memória deverá distinguir, conforme aplicável:

- Informações recentes das conversas.
- Preferências recorrentes e configurações do usuário.
- Projetos, objetivos, decisões e tarefas em andamento.
- Conhecimento consolidado e fatos relevantes.
- Eventos, ações executadas e seus respectivos resultados.
- Rotinas identificadas e comportamentos que ainda precisam de confirmação.

As informações importantes deverão ter origem e contexto identificáveis. O Jarvis não deverá tratar uma hipótese como fato confirmado nem considerar permanentemente atual uma informação que possa ter mudado.

Quando encontrar informações contraditórias, deverá reconhecer o conflito, avaliar as evidências disponíveis e solicitar ajuda quando não houver uma resolução confiável.

A memória não deverá crescer descontroladamente. O sistema deverá organizar, resumir, arquivar e remover informações de acordo com políticas claras de relevância, retenção e privacidade, sem apagar silenciosamente dados importantes.

### 5. Planejamento e execução de tarefas

O Jarvis deverá ser capaz de receber objetivos e transformá-los em tarefas executáveis.

Para cada tarefa relevante, deverá conseguir:

1. Compreender o objetivo e os critérios de sucesso.
2. Identificar informações, ferramentas, permissões e recursos necessários.
3. Planejar uma sequência de etapas.
4. Avaliar riscos, custos, disponibilidade e incertezas.
5. Executar as ações permitidas.
6. Verificar os resultados por meio de evidências reais.
7. Corrigir falhas recuperáveis ou apresentar alternativas.
8. Comunicar o resultado final e registrar as informações importantes.

Tarefas maiores deverão ser divididas em etapas menores, com progresso observável e possibilidade de cancelamento.

Quando houver dependências, falhas ou falta de recursos, o Jarvis deverá ajustar o plano em vez de fingir que concluiu a atividade.

O sistema poderá utilizar agentes especializados para tarefas diferentes, mas deverá manter coordenação central, limites de permissão e rastreabilidade. A criação de múltiplos agentes não deverá duplicar responsabilidades nem conceder autonomia irrestrita a cada um.

### 6. Uso inteligente de modelos e recursos computacionais

O Jarvis deverá selecionar os recursos de inteligência artificial de acordo com as características de cada tarefa, considerando qualidade necessária, latência, custo, privacidade, conectividade e recursos disponíveis.

Quando adequado, poderá utilizar modelos locais e gratuitos. Quando necessário e autorizado, poderá recorrer a APIs ou modelos externos.

O sistema deverá avaliar as capacidades reais de cada nó e encaminhar tarefas de acordo com seus requisitos. Não deverá enviar automaticamente uma tarefa para um computador sem memória suficiente, para um serviço indisponível ou para um provedor incompatível.

O funcionamento distribuído deverá permitir expansão gradual: adicionar um computador ou serviço compatível deverá aumentar as capacidades do sistema sem exigir uma reconstrução completa da arquitetura.

A indisponibilidade de um nó ou provedor deverá provocar uma resposta controlada. O Jarvis poderá tentar novamente, selecionar um recurso alternativo ou informar que não consegue prosseguir.

Não deverá afirmar que executou uma tarefa quando não houver confirmação confiável do resultado.

### 7. Autonomia, proatividade e controle do usuário

O Jarvis deverá ser proativo. Poderá identificar tarefas pendentes, oportunidades relevantes, possíveis problemas e rotinas úteis, apresentando sugestões no momento adequado.

Entretanto, sua autonomia deverá seguir uma política explícita de risco e autorização.

- **Ações de baixo risco:** poderão ser executadas automaticamente quando houver permissão explícita e critérios definidos.
- **Ações com consequências relevantes:** deverão respeitar as regras de confirmação estabelecidas para a categoria da ação.
- **Ações sensíveis, destrutivas, irreversíveis, financeiras ou de alto risco:** deverão exigir autorização apropriada antes da execução.
- **Ações sem permissão ou incompatíveis com as políticas:** deverão ser bloqueadas.

As confirmações deverão informar claramente o que será feito, em qual recurso, com qual consequência e dentro de quais limites. Uma autorização deverá ser específica, verificável e limitada ao tempo ou ao escopo previsto.

O Jarvis deverá aprender possíveis rotinas com o uso, mas não deverá presumir que observar um comportamento significa ter permissão para repeti-lo automaticamente.

O usuário deverá poder consultar, corrigir, pausar e revogar automações, agentes, integrações e permissões.

### 8. Ferramentas, computadores e dispositivos conectados

Com as integrações correspondentes instaladas e autorizadas, o Jarvis deverá conseguir interagir com recursos digitais e dispositivos físicos compatíveis.

Isso poderá incluir gerenciamento de arquivos, execução de ferramentas, desenvolvimento de software, consulta a serviços, monitoramento de sistemas e automação residencial por meio do Home Assistant.

Cada integração deverá declarar suas capacidades, pré-requisitos, permissões, limites e possíveis efeitos colaterais.

O Jarvis deverá verificar o estado real de um recurso antes de realizar uma ação que dependa desse estado e, depois, confirmar o resultado quando houver um mecanismo confiável para isso.

Por exemplo, ao receber uma solicitação para ligar uma luz, deverá utilizar a integração autorizada e verificar o estado informado pelo sistema. Não deverá afirmar que a luz foi ligada apenas porque enviou um comando.

O modelo de linguagem não deverá executar comandos de sistema arbitrários sem validação. A execução deverá passar por ferramentas controladas, políticas de autorização, validação de parâmetros e registros apropriados.

### 9. Estado do mundo e tratamento da incerteza

O Jarvis deverá manter uma representação contextual das informações relevantes para suas decisões, combinando dados de ferramentas, serviços, dispositivos, memória e entradas do usuário.

Essa representação deverá distinguir estados:

- Observados diretamente.
- Inferidos a partir de evidências.
- Planejados, mas ainda não executados.
- Previstos.
- Desconhecidos.
- Desatualizados.

Quando uma informação for dinâmica, o Jarvis deverá consultar a fonte apropriada antes de depender dela, sempre que isso for necessário e permitido.

Quando houver contradição ou evidência insuficiente, deverá comunicar a incerteza de forma proporcional à importância da decisão.

O grau de confiança de um modelo nunca deverá substituir uma verificação real, uma regra de segurança ou uma autorização do usuário.

### 10. Autocorreção e evolução controlada

O Jarvis deverá conseguir monitorar sua própria operação, identificar falhas e tentar recuperar componentes quando isso for seguro.

Poderá executar diagnósticos, reiniciar serviços permitidos, repetir operações recuperáveis, restaurar estados conhecidos e propor correções de código.

Mudanças no próprio sistema deverão seguir um processo controlado:

1. Identificar o problema e reunir evidências.
2. Preparar a alteração em um ambiente apropriado.
3. Executar testes e validações.
4. Avaliar os resultados e possíveis efeitos colaterais.
5. Disponibilizar a mudança conforme as políticas de aprovação.
6. Monitorar o resultado e reverter a alteração quando necessário.

Sempre que possível, as alterações deverão ter histórico, backup e um caminho de reversão testado.

O Jarvis não poderá modificar as próprias políticas de segurança para liberar uma ação bloqueada, conceder permissões a si mesmo, apagar evidências de auditoria ou desativar mecanismos de proteção para fazer uma correção passar.

A capacidade de melhorar o próprio funcionamento deverá aumentar a confiabilidade do sistema, e não tornar suas decisões imprevisíveis.

### 11. Segurança, privacidade e recuperação

A segurança deverá ser uma propriedade permanente da arquitetura, e não um recurso opcional.

O Jarvis deverá aplicar autenticação, autorização, mínimo privilégio, proteção de credenciais, isolamento de sessões, validação de entradas, limites operacionais e registros auditáveis.

Informações sensíveis deverão ser processadas localmente quando apropriado e tecnicamente possível. Qualquer envio a provedores externos deverá respeitar as configurações e permissões aplicáveis.

O sistema deverá possuir mecanismos de backup, verificação de integridade e restauração testada. Uma falha de disco, corrupção de dados, atualização problemática ou indisponibilidade de um componente não deverá provocar perda evitável de todo o sistema.

Credenciais, dados pessoais e conteúdo sensível não deverão ser expostos indevidamente em logs, notificações, prompts ou interfaces de diagnóstico.

A recuperação de desastres deverá fazer parte do funcionamento operacional documentado, com procedimentos comprovados em ambiente de teste.

### 12. Instalação, manutenção e experiência de uso

O Jarvis deverá ser instalável, configurável, atualizável e recuperável por processos claros e reproduzíveis.

Deverá oferecer perfis de instalação adequados aos ambientes suportados, como SERVER, CORE/AI NODE e All-in-One, sem duplicar desnecessariamente a lógica do produto.

O instalador deverá verificar os pré-requisitos, orientar a configuração inicial, identificar problemas e validar a saúde do sistema. A instalação não deverá abrir portas públicas nem habilitar permissões perigosas por padrão.

As atualizações deverão considerar a compatibilidade de configurações, migrações de dados, integridade da memória e possibilidade de reversão.

O sistema também deverá oferecer logs compreensíveis, diagnósticos úteis, estado dos componentes, informações sobre tarefas e documentação suficiente para operação sem depender exclusivamente de uma IA para resolver qualquer problema.

### 13. Critérios para considerar o Jarvis completo

A conclusão do roadmap não deverá ser determinada apenas pela existência de arquivos, classes, interfaces ou funcionalidades demonstrativas.

Cada capacidade importante deverá ter critérios de aceitação, documentação e testes correspondentes. Funcionalidades críticas deverão ser validadas em condições realistas, incluindo erros de rede, reinicializações, indisponibilidade de serviços, permissões negadas, recursos insuficientes e recuperação de falhas.

Mocks poderão validar comportamentos isolados, mas não deverão ser considerados prova suficiente de integração real entre dispositivos, serviços ou sistemas operacionais.

Antes de declarar o projeto concluído, deverá ser possível demonstrar que:

- Os componentes se comunicam e mantêm o estado de maneira consistente.
- Conversas, memórias e tarefas persistem conforme o comportamento documentado.
- A execução de ferramentas respeita permissões e verifica resultados.
- A autonomia não ultrapassa os limites definidos.
- Os nós distribuídos são detectados e utilizados de maneira controlada.
- Os mecanismos de backup e restauração funcionam em testes reais.
- As falhas são identificadas e tratadas sem falsas declarações de sucesso.
- A instalação, a configuração e a atualização funcionam nos ambientes oficialmente suportados.
- A documentação corresponde à implementação e aos testes realmente executados.
- O sistema pode ser utilizado, monitorado, atualizado e recuperado de forma sustentável.

Uma funcionalidade deverá ser marcada como concluída somente quando houver evidência suficiente para sustentar essa afirmação. Capacidades ainda não implementadas, não testadas ou dependentes de serviços externos deverão ser identificadas explicitamente.

### Resultado final esperado

Ao final de todas as fases, o Jarvis deverá ser um assistente pessoal que permanece disponível, mantém contexto ao longo do tempo, entende objetivos, planeja tarefas, utiliza ferramentas e recursos distribuídos, automatiza atividades autorizadas, conecta-se a dispositivos compatíveis e melhora sua confiabilidade por meio de diagnósticos e correções controladas.

Deverá combinar autonomia com supervisão, memória com privacidade, inteligência com evidências e flexibilidade com regras de segurança.

O sistema deverá conseguir realizar trabalho útil de ponta a ponta: compreender uma solicitação, preparar e executar um plano permitido, verificar o resultado, preservar o contexto necessário e explicar o que foi feito.

A visão final não é criar uma IA com acesso ilimitado a tudo, mas construir um assistente confiável, extensível e verdadeiramente útil, capaz de utilizar os recursos aos quais recebeu acesso sem perder o controle do estado, das permissões ou das consequências de suas ações.

**Princípio definitivo:** o Jarvis deverá ser capaz de pensar sobre o que precisa fazer, planejar como fazer, executar o que está autorizado a fazer, verificar se realmente funcionou, aprender com o resultado e se recuperar de falhas — sem inventar resultados, ocultar incertezas ou ultrapassar as permissões do usuário.
