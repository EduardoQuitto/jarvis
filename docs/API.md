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
Lista todas as ferramentas registradas no nó com seus respectivos esquemas JSON Schema e níveis de segurança.

### 4. `POST /tools/execute`
Executa uma ferramenta registrada após validação de políticas no `PolicyEngine`.
* **Corpo da Requisição:**
```json
{
  "tool_name": "launch_application",
  "parameters": {
    "app_name": "notepad"
  },
  "confirmed": true
}
```
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
