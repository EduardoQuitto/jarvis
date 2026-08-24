# J.A.R.V.I.S. — Sistema de Ferramentas (Tool System)

## 1. Estrutura do Sistema

O sistema de ferramentas fornece uma interface tipada, assíncrona e segura para execução de ações no sistema operacional e nós da rede.

```python
class BaseTool(ABC):
    name: str
    description: str
    security_level: SecurityLevel
    visibility: ToolVisibility  # LOCAL_ONLY (default) ou SHARED
    args_schema: Optional[Type[BaseModel]]
    timeout_seconds: float

    async def execute(self, **kwargs: Any) -> ToolResult:
        pass
```

### Visibilidade (`ToolVisibility`)
* `LOCAL_ONLY` (padrão): tool visível apenas para provedores locais. Protege informação sensível do sistema de provedores externos.
* `SHARED`: tool visível para todos os provedores (local + externo).

---

## 2. Ferramentas Built-in Disponíveis

### 🟢 GREEN — Execução Automática

| Tool | Descrição | Parâmetros | Visibilidade |
|------|-----------|------------|--------------|
| `get_system_metrics` | Coleta dados reais de hardware (CPU, RAM, disco, GPU). | Nenhum | LOCAL_ONLY |
| `list_processes` | Lista processos ativos com consumo de CPU/memória. | `limit`, `sort_by` | LOCAL_ONLY |
| `echo` | Ferramenta diagnóstica para teste de conectividade. | `message` | **SHARED** |
| `get_current_time` | Retorna data e hora atuais. | Nenhum | **SHARED** |
| `web_search` | Busca na web via DuckDuckGo. | `query`, `max_results` | **SHARED** |
| `fetch_url` | Busca conteúdo de uma URL com proteção anti-SSRF. | `url`, `timeout` | **SHARED** |

### 🟡 YELLOW — Exige Confirmação

| Tool | Descrição | Parâmetros | Visibilidade |
|------|-----------|------------|--------------|
| `launch_application` | Inicia uma aplicação aprovada na allowlist. | `app_name` | LOCAL_ONLY |
| `close_application` | Encerra instâncias de uma aplicação permitida. | `app_name` | LOCAL_ONLY |
| `read_file` | Lê conteúdo de um arquivo. | `file_path` | LOCAL_ONLY |
| `write_file` | Escreve conteúdo em um arquivo. | `file_path`, `content` | LOCAL_ONLY |
| `list_dir` | Lista conteúdo de um diretório. | `directory` | LOCAL_ONLY |

---

## 3. Segurança de Tools

### ConfirmationManager
* Cada tool YELLOW/RED gera um `confirmation_id` (cid).
* cid é **single-use** e vinculado à `session_id`.
* Após consumo, cid é removido do cache.
* LLM, MCP e StepExecutor nunca definem `confirmed=True`.

### Provider Trust Filtering
* Tools marcadas `LOCAL_ONLY` (padrão) são filtradas quando o próximo provedor é externo.
* Apenas tools `SHARED` são enviadas para provedores externos (Groq, Together, OpenRouter).
* Isso impede que provedores externos vejam tools como `read_file`, `launch_application`, etc.

### SSRF Protection (fetch_url)
* Validação de URL via `security/net_guard.py`.
* Bloqueia IPs privados/loopback/link-local por padrão.
* Redirect hop-by-hop com validação em cada hop (máx 5).
* Opt-in para LAN via `JARVIS_NET_ALLOW_PRIVATE_NETWORKS`.

### File Sandbox (read_file, write_file, list_dir)
* Validação via `AllowlistValidator.validate_file_path()`.
* Resolve symlinks antes de validar.
* Usa `relative_to()` para containment (previne prefix trick).
* Bloqueia paths fora de `allowed_paths`.

---

## 4. Registro e Uso

```python
from tools.registry import get_tool_registry
from tools import register_default_tools

registry = get_tool_registry()
register_default_tools(registry)

# Listar tools
tools = registry.list_tools()

# Executar tool
result = await registry.execute_tool(
    name="echo",
    parameters={"message": "Hello"},
)
```
