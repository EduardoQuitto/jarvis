# J.A.R.V.I.S. — Modelo de Segurança

## 1. Níveis de Classificação de Segurança

O sistema adota estritamente a política de 3 cores definida nas diretrizes do projeto:

### 🟢 Nível Verde (GREEN) — Execução Automática
* **Ações Permitidas:** Consultas de telemetria (CPU, RAM, Disco, GPU), listagem de processos ativos, leituras seguras de estado, ping/echo.
* **Comportamento:** Executadas diretamente pelo `PolicyEngine` sem intervenção do usuário.

### 🟡 Nível Amarelo (YELLOW) — Exige Confirmação
* **Ações Permitidas:** Inicialização de aplicativos da allowlist, encerramento de processos autorizados, reinicialização controlada de serviços.
* **Comportamento:** O `PolicyEngine` bloqueia a execução e retorna status `REQUIRE_APPROVAL` a menos que o parâmetro `confirmed=True` ou token de aprovação seja explicitamente enviado.

### 🔴 Nível Vermelho (RED) — Exige Autorização Explícita
* **Ações Permitidas:** Exclusão de arquivos, alteração de credenciais, configurações críticas de firewall e rede.
* **Comportamento:** Bloqueadas por padrão e exigem confirmação reforçada de alto privilégio.

---

## 2. Prevenção de Shell Arbitrário & Injeção

É terminantemente proibida a criação de endpoints de shell arbitrário (ex: `/execute?cmd=...`).
* **Allowlist de Aplicações:** O `AllowlistValidator` mapeia aliases pré-definidos (ex: `notepad`, `calc`, `vscode`, `unity`) para seus executáveis aprovados.
* **Sanitização de Metacaracteres:** O validador rejeita strings contendo caracteres de encadeamento de comandos (`&`, `|`, `;`, `>`, `<`, `` ` ``, `$`, `\n`, `\r`).
* **Path Sandboxing:** Valida que qualquer caminho de arquivo esteja dentro das raízes autorizadas (`allowed_paths`) prevenindo ataques de *Directory Traversal*.

---

## 3. Autenticação Inter-Nós

* Todas as rotas de gerenciamento e ferramentas do `server/` exigem autenticação via Bearer Token / API Key com validação em tempo constante (`hmac.compare_digest`).
