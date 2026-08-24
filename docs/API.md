# J.A.R.V.I.S. — Especificação da API REST

A API do nó JARVIS é desenvolvida em **FastAPI** e provê endpoints para diagnóstico, telemetria em tempo real e execução segura de ferramentas.

## Autenticação

Todas as requisições autenticadas exigem o cabeçalho HTTP:
```http
Authorization: Bearer <JARVIS_API_KEY>
```

---

## Endpoints

### 1. `GET /health`
Retorna a saúde geral do nó, quantidade de ferramentas registradas e resumo de hardware.
* **Autenticação:** Obrigatória.
* **Exemplo de Resposta (200 OK):**
```json
{
  "status": "healthy",
  "node_id": "node2-dev",
  "node_role": "NODE2",
  "registered_tools_count": 5,
  "system": {
    "node_id": "node2-dev",
    "os_name": "Windows",
    "os_version": "10.0.19045",
    "uptime_seconds": 15420.0,
    "cpu": {
      "usage_percent": 12.4,
      "cores_logical": 2,
      "cores_physical": 2
    },
    "memory": {
      "total_bytes": 8589934592,
      "available_bytes": 4294967296,
      "used_bytes": 4294967296,
      "usage_percent": 50.0
    }
  },
  "gpu": null
}
```

### 2. `GET /telemetry`
Retorna métricas detalhadas em tempo real de CPU, RAM, discos e processos.

### 3. `GET /tools`
Lista todas as ferramentas registradas no nó com seus respectivos esquemas JSON Schema, níveis de segurança e visibilidade.

### 4. `POST /tools/execute`
Executa uma ferramenta registrada após validação de políticas no `PolicyEngine`.
* **Corpo da Requisição:**
```json
{
  "tool_name": "launch_application",
  "parameters": {
    "app_name": "notepad"
  },
  "operator_direct": true
}
```
* **Nota:** `operator_direct` substitui o antigo campo `confirmed`. Apenas o operador via REST pode definir `operator_direct=true`. LLM, MCP e StepExecutor nunca definem esse campo.

* **Resposta (200 OK):**
```json
{
  "success": true,
  "data": {
    "launched": true,
    "app_name": "notepad",
    "executable": "notepad.exe",
    "pid": 12480
  },
  "error": null,
  "execution_time_ms": 15.2,
  "security_level": "YELLOW"
}
```

---

## Chat API

### 5. `POST /chat`
Endpoint principal de interação com o assistente.
* **Corpo da Requisição:**
```json
{
  "message": "launch notepad",
  "session_id": "sess-abc123"
}
```
* **Resposta — GREEN tool (200 OK):**
```json
{
  "status": "ok",
  "response": "Notepad has been launched.",
  "session_id": "sess-abc123",
  "tool_used": "launch_application",
  "execution_time_ms": 150
}
```
* **Resposta — YELLOW tool (200 OK):**
```json
{
  "status": "needs_confirmation",
  "confirmation_id": "confirm-xxx",
  "tool_name": "launch_application",
  "arguments": {"app_name": "notepad"},
  "security_level": "YELLOW",
  "reason": "Tool 'launch_application' is classified YELLOW"
}
```
* **Resposta — YELLOW tool aprovado (200 OK):**
```json
{
  "status": "ok",
  "response": "Notepad has been launched successfully.",
  "session_id": "sess-abc123"
}
```

### Fluxo de Confirmação
1. Usuário envia mensagem que requer tool YELLOW/RED.
2. Orchestrator retorna `needs_confirmation` + `confirmation_id`.
3. Usuário aprova: `POST /chat` com mesma `message` + `approved=true` + `session_id`.
4. Orchestrator confirma → consome cid (single-use) → executa tool → LLM gera resumo.

---

## MCP Server (JSON-RPC 2.0)

### 6. `POST /mcp`
Endpoint MCP para clientes externos.
* **Métodos suportados:** `initialize`, `tools/list`, `tools/call`, `ping`.
* **Política de segurança:**
  - GREEN tools: executam normalmente.
  - YELLOW/RED tools: retornam erro `requires_confirmation` ao cliente MCP.
  - MCP nunca bypassa confirmação.

---

## Configuração

Variáveis de ambiente relevantes (via `.env` ou `core/config.py`):
```env
JARVIS_API_KEY=your-secret-key
JARVIS_EXTERNAL_LLM_API_KEY=gsk_...
JARVIS_EXTERNAL_LLM_BASE_URL=https://api.groq.com/openai/v1
JARVIS_EXTERNAL_LLM_MODEL=llama-3.3-70b-versatile
JARVIS_NET_ALLOW_PRIVATE_NETWORKS=["192.168.1.0/24"]  # opt-in LAN access
```
