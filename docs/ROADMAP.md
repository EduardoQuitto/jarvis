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
- [x] Descoberta do CORE via `DeviceRegistry`.
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

1. Ligar o Ubuntu Server.
2. Conferir/configurar manualmente o `.env` do SERVER, incluindo a credencial Gemini **somente no SERVER**.
3. Iniciar/reiniciar o serviço JARVIS no Ubuntu.
4. Verificar schema/migração da base central e saúde do SERVER.
5. Iniciar o CORE Windows e confirmar registro + heartbeat no SERVER.
6. Testar fluxo real **cliente → SERVER → CORE → Ollama → SERVER → cliente**.
7. Testar fluxo **CORE → SERVER relay → Gemini → SERVER → CORE**, garantindo que a chave Gemini não exista no CORE.
8. Testar conversação, memória e confirmations centralizadas.
9. Testar `POST /api/chat/stream` real e comportamento em falha/desconexão.
10. Confirmar logs, status dos dispositivos e ausência de secrets no Git.

**Não implementar nesta validação:** VPN/acesso externo, Home Assistant, voz, visão, Android ou novos bancos/filas.

---

## Fases Futuras

### 🔐 Fase 13: Acesso Externo Seguro
- [ ] Permitir uso do JARVIS fora de casa através de **rede privada/VPN**.
- [ ] SERVER permanece como único gateway da arquitetura.
- [ ] Não expor diretamente o CORE ou ferramentas sensíveis à internet pública.
- [ ] Autenticação, autorização e mínimo privilégio para clientes externos.
- [ ] Reconexão e disponibilidade quando a conexão externa cair.
- [ ] Observabilidade do acesso remoto sem criar dependência de exposição pública.
- [ ] Não implementar até a Fase 12 estar validada localmente.

### 🏠 Fase 14: Integração Home Assistant
- [ ] Home Assistant como backbone de automação doméstica.
- [ ] Scheduler e automações no SERVER.
- [ ] Wake-on-LAN para acordar o CORE quando necessário.
- [ ] Controle de dispositivos e cenas.
- [ ] SERVER continua leve; processamento pesado permanece no CORE.
- [ ] Integração deve respeitar o mesmo modelo central de identidade, estado e autorização.

### 🎙️ Fase 15: Pipeline de Voz Local
- [ ] Wake Word.
- [ ] VAD (detecção de atividade de voz).
- [ ] STT local, inicialmente com Whisper ou alternativa equivalente.
- [ ] TTS local, inicialmente com Piper ou alternativa equivalente.
- [ ] Fluxo completo: Wake Word → VAD → STT → Orchestrator → Tool/LLM → TTS.
- [ ] Voz deve utilizar o mesmo JARVIS central, memória, Goals e segurança.
- [ ] Não criar uma segunda inteligência paralela.

### 📱 Fase 16: Android & Tablet Dashboard
- [ ] Priorizar Home Assistant Companion e/ou ADB para integração Android.
- [ ] Telemetria, notificações, câmera, microfone e sensores.
- [ ] Comunicação do S20 com o SERVER central.
- [ ] Painel leve para tablet.
- [ ] Avaliar Termux/Termux:API quando um agente local Android for realmente necessário.
- [ ] Avaliar posteriormente um **canal telefônico/número próprio do JARVIS**, usando APIs oficiais e arquitetura separada.
- [ ] Ações sensíveis no Android continuam passando pelo modelo de segurança do JARVIS.
- [ ] O canal telefônico deve tratar identidade, autorização, logs e limites de uso antes de permitir ações reais.

### 👁️ Fase 17: Visão Computacional
- [ ] Captura de tela.
- [ ] OCR quando necessário.
- [ ] Análise visual local.
- [ ] Integração com o contexto do Orchestrator.
- [ ] Separar percepção visual de planejamento e execução.
- [ ] A percepção visual nunca deve conceder autorização automaticamente.
- [ ] Preparar a base necessária para Computer Use da Fase 20.

### 🧠 Fase 18: Memória Vetorial & Busca Semântica
- [ ] Adicionar embeddings locais e busca semântica.
- [ ] Integrar a busca semântica à **memória central já existente**.
- [ ] SERVER continua sendo a autoridade do estado persistente.
- [ ] Avaliar ChromaDB ou alternativas antes de adicionar dependências.
- [ ] Evitar duplicação de memória entre SERVER e CORE.
- [ ] SQLite continua como camada fundamental de estado e auditoria.
- [ ] A memória vetorial deve resolver um problema real de recuperação contextual, e não apenas aumentar complexidade.
- [ ] Definir política de retenção, indexação, atualização e exclusão.
- [ ] Recuperação semântica deve respeitar permissões e isolamento de dados.

### 🤖 Fase 19: Autonomia Progressiva & Goal-Driven Intelligence
- [ ] Evoluir o fluxo **Goal → Plan → Steps → Execution → Observation → Evaluation → Replanning**.
- [ ] Integrar de forma realmente operacional `GoalEngine`, `Planner` e `Orchestrator`.
- [ ] Substituir o replanning puramente hardcoded por decisões orientadas por contexto/LLM quando houver segurança para isso.
- [ ] Permitir estratégias como retry, ferramenta alternativa, decomposição, subgoal, mudança de abordagem e solicitação de ajuda.
- [ ] Evitar parada artificial após poucas tentativas quando ainda houver estratégias seguras disponíveis.
- [ ] Persistir progresso, tentativas, decisões, erros e motivos.
- [ ] Permitir retomada de Goals longos após interrupções.
- [ ] Trabalhar com orçamento de tokens, tempo, ferramentas e limites de execução.
- [ ] Supervisão humana para decisões críticas.
- [ ] Validar cada etapa antes de permitir que a próxima ação material seja executada.
- [ ] Não confundir autonomia com ausência de controle do usuário.
- [ ] Evoluir o `IntelligenceRouter` para diferenciar necessidades de **thinking/reasoning** e **action/execution**.
- [ ] Avaliar uma arquitetura com modelo maior para planejamento/raciocínio e modelo menor para ações rotineiras, por exemplo Qwen 3.5 9B e Qwen 3.5 4B.
- [ ] O uso de 9B/4B é uma estratégia de referência e não um acoplamento rígido da arquitetura.
- [ ] O router deve decidir pelo tipo e necessidade da tarefa, não apenas pelo nome do modelo.
- [ ] Manter fallback entre modelos/providers sem inventar estado quando um provider falhar.
- [ ] Metas de longa duração devem continuar usando o mesmo estado central do SERVER.

### 🖱️ Fase 20: Computer Use Seguro
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

### 🧬 Fase 21: Self-Editing & Self-Evolution Seguro
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
- [ ] Self-editing deve usar as mesmas políticas de segurança e confirmação do restante do JARVIS.

### 📊 Fase 22: Observabilidade, Benchmarks & Eficiência
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

### 🧩 Fase 23: Plugin System & Extensibilidade
- [ ] Sistema de extensões/plugins com contratos claros.
- [ ] Descoberta e registro controlados.
- [ ] Permissões por plugin.
- [ ] Isolamento de plugins não confiáveis.
- [ ] Compatibilidade com ferramentas locais, remotas e futuras integrações.
- [ ] Plugins devem declarar capacidades e requisitos de forma explícita.
- [ ] Nenhum plugin deve contornar `PolicyEngine`, `ToolVisibility` ou autenticação.
- [ ] Plugins devem possuir ciclo de vida controlado e possibilidade de desativação.

### 🔭 Fase 24: Multi-Modalidade Integrada
- [ ] Unificar texto, voz, visão e interfaces externas em um mesmo contexto de sessão.
- [ ] Compartilhar memória, objetivos e estado entre modalidades.
- [ ] Manter uma única autoridade de estado no SERVER.
- [ ] Usar o CORE para processamento pesado multimodal.
- [ ] Preservar os mesmos limites de segurança independentemente da interface.
- [ ] Permitir transição natural entre texto, voz, imagem, tela e dispositivos.
- [ ] Manter identidade e contexto consistentes em todas as modalidades.

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
- [ ] O SERVER continua sendo **control plane / source of truth**.
- [ ] O CORE continua sendo **compute plane**.
- [ ] O hardware deve continuar desacoplado do desenho de software.
- [ ] O acesso externo futuro deve ocorrer por rede privada segura, nunca por exposição direta de serviços internos.
- [ ] Autonomia deve aumentar a capacidade de executar objetivos mantendo supervisão e controle humano onde necessário.

---

### Nota sobre Hardware

O NODE 2 foi originalmente um Pentium G3260. Foi atualizado para um i5-7400 com 8 GB RAM, SSD ~222 GB e HDD 500 GB. O código é projetado para ser portátil e não é otimizado para hardware específico.