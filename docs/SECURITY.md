# J.A.R.V.I.S. — Modelo de Segurança

## 1. Níveis de Classificação de Segurança

O sistema adota estritamente a política de 3 cores definida nas diretrizes do projeto:

### 🟢 Nível Verde (GREEN) — Execução Automática
* **Ações Permitidas:** Consultas de telemetria (CPU, RAM, Disco, GPU), listagem de processos ativos, leituras seguras de estado, ping/echo.
* **Comportamento:** Executadas diretamente pelo `PolicyEngine` sem intervenção do usuário.

### 🟡 Nível Amarelo (YELLOW) — Exige Confirmação
* **Ações Permitidas:** Inicialização de aplicativos da allowlist, encerramento de processos autorizados, reinicialização controlada de serviços.
* **Comportamento:** O `PolicyEngine` bloqueia a execução e retorna status `needs_confirmation` com `confirmation_id` (cid). Fluxo:
  1. Usuário envia mensagem.
  2. LLM responde com tool call YELLOW.
  3. Orchestrator verifica PolicyEngine → `requires_confirmation=True`.
  4. Orchestrator armazena na ConfirmationManager → retorna `needs_confirmation` + cid.
  5. Usuário aprova via REST com `approved=true` e mesmo `message`.
  6. Orchestrator: confirma → consome cid (single-use) → executa tool → LLM gera resumo.

### 🔴 Nível Vermelho (RED) — Exige Autorização Explícita
* **Ações Permitidas:** Exclusão de arquivos, alteração de credenciais, configurações críticas de firewall e rede.
* **Comportamento:** Bloqueadas por padrão e exigem confirmação reforçada de alto privilégio.

---

## 2. Prevenção de Shell Arbitrário & Injeção

É terminantemente proibida a criação de endpoints de shell arbitrário (ex: `/execute?cmd=...`).
* **Allowlist de Aplicações:** O `AllowlistValidator` mapeia aliases pré-definidos (ex: `notepad`, `calc`, `vscode`, `unity`) para seus executáveis aprovados.
* **Sanitização de Metacaracteres:** O validador rejeita strings contendo caracteres de encadeamento de comandos (`&`, `|`, `;`, `>`, `<`, `` ` ``, `$`, `\n`, `\r`).
* **Path Sandboxing:** Valida que qualquer caminho de arquivo esteja dentro das raízes autorizadas (`allowed_paths`) prevenindo ataques de *Directory Traversal* e symlink manipulation.

---

## 3. Autenticação Inter-Nós

* Todas as rotas de gerenciamento e ferramentas do `server/` exigem autenticação via Bearer Token / API Key com validação em tempo constante (`hmac.compare_digest`).

---

## 4. Confirmação — Regras de Segurança

### ConfirmationManager
* Cada confirmação possui `session_id` e `call_id` vinculados.
* `consume(cid, session_id)` é **single-use**: após consumir, a confirmação é removida.
* Se `session_id` não bate com o da sessão que criou, retorna `None`.
* Confirmações expiram após `default_timeout` (5 minutos por padrão).
* LLM, MCP e StepExecutor **NUNCA** definem `confirmed=True` internamente.
* Apenas o operador (REST ou chat com `approved=true`) pode confirmar.

### Fluxo de Confirmação
```
User → "launch notepad"
Orchestrator → PolicyEngine.evaluate(YELLOW) → needs_confirmation
Orchestrator → ConfirmationManager.request_confirmation(tool, args, session_id)
Orchestrator → returns {status: "needs_confirmation", confirmation_id: "confirm-xxx"}

User (REST) → POST /chat {message: "launch notepad", approved: true, confirmation_id: "confirm-xxx"}
Orchestrator → ConfirmationManager.approve(cid) → ConfirmationManager.consume(cid, session_id)
Orchestrator → execute tool → LLM summarizes → returns {status: "ok", response: "Notepad launched."}
```

---

## 5. Provider Trust & Tool Visibility

### Visibilidade de Tools
* `ToolVisibility.LOCAL_ONLY` (padrão): tool visível apenas para provedores locais.
* `ToolVisibility.SHARED`: tool visível para todos os provedores (local + externo).

Tools marcadas como SHARED: `echo`, `get_current_time`, `web_search`, `fetch_url`.

### Filtro por Provedor
* `ProviderRegistry` possui campo `local: bool` em `ProviderEntry`.
* Provedores externos registrados com `local=False`.
* `IntelligenceRouter.is_next_provider_local()` verifica o próximo provedor da cadeia.
* `ContextBuilder.build_tools_list(shared_only=True)` filtra por visibility.
* Orchestrator pergunta ao router antes de chamar LLM: se externo, só envia SHARED tools.

### Por quê?
Tools locais (read_file, launch_application, list_dir) expõem informação sensível do sistema. Provedores externos (Groq, Together, OpenRouter) não devem ter acesso a essas tools.

---

## 6. Proteção Anti-SSRF (Server-Side Request Forgery)

### NetGuard (`security/net_guard.py`)
* Bloqueia requisições para IPs privados/loopback/link-local por padrão:
  - `127.0.0.0/8` (loopback IPv4)
  - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (privados)
  - `169.254.0.0/16` (link-local)
  - `::1/128`, `fc00::/7`, `fe80::/10` (IPv6)
  - `0.0.0.0/8`, `100.64.0.0/10` (reservados)
* Validação de URL: scheme http/https, sem credenciais, sem localhost.
* DNS resolution + verificação de IP resultante.
* Redirect hop-by-hop: cada redirect é validado separadamente (máx 5 hops).
* **Opt-in para LAN**: `JARVIS_NET_ALLOW_PRIVATE_NETWORKS=["192.168.1.0/24"]` permite ranges específicos.

### FetchUrlTool
* Usa NetGuard para validar URL inicial.
* `follow_redirects=False`: seguidor manual de redirects com validação em cada hop.
* `validate_redirect_url()` valida cada Location header.

### FileTool
* Usa `AllowlistValidator.validate_file_path()` que:
  - Resolve symlinks antes de validar.
  - Usa `relative_to()` para containment (não `startswith` — previne prefix trick).
  - Bloqueia paths fora de `allowed_paths`.

---

## 7. Testes de Segurança

### Suite de testes (153 total)
* `test_confirmation.py` (9): approve→consume, deny→consume, single-use, session mismatch, wait timeout, list_pending.
* `test_mcp_policy.py` (4): GREEN accepted, YELLOW requires confirmation, YELLOW blocked in MCP, YELLOW allowed if confirmed.
* `test_provider_visibility.py` (3): local sees all, external sees only SHARED, empty when no shared.
* `test_net_guard.py` (21): scheme/credentials/localhost/loopback/private/link-local/DNS failure/redirects, opt-in CIDR, _is_ip_blocked unit tests.
* `test_file_sandbox.py` (6): valid file, prefix trick, dot-dot traversal, absolute outside, symlink outside, symlink inside.

### Execução
```bash
python -m pytest -q --no-header -p no:cacheprovider
# Resultado: 153 passed, 0 failed, exit 0
# data/jarvis.db inalterado (D8A125F20EB72BEBE45D0378CECED2A2)
```
