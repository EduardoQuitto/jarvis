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

---

## 5. Agent System

### AgentFactory
Cria agentes especializados com permissões controladas:

```python
from core.agent.factory import get_agent_factory

factory = get_agent_factory()

# Research agent — apenas tools SHARED
agent = factory.create_research_agent(
    name="Pesquisador",
    objective="Pesquisar frameworks de teste",
)

# Developer agent — acesso a files
agent = factory.create_developer_agent(
    name="Desenvolvedor",
    objective="Escrever código",
)

# Analyst agent — métricas do sistema
agent = factory.create_analyst_agent(
    name="Analista",
    objective="Analisar performance",
)

# Critic agent — revisão
agent = factory.create_critic_agent(
    name="Crítico",
    objective="Revisar código",
)

# Custom agent
agent = factory.create_agent(
    agent_type="custom",
    name="Meu Agente",
    objective="Tarefa específica",
    tool_allowlist=["echo", "web_search"],
    max_iterations=5,
)
```

### Tipos de Agent
| Tipo | Tools | max_iterations | LOCAL_ONLY |
|------|-------|----------------|------------|
| research | echo, get_current_time, web_search, fetch_url | 10 | Não |
| developer | echo, get_current_time, web_search, fetch_url, read_file, write_file, list_dir | 15 | Sim |
| analyst | echo, get_current_time, get_system_metrics, list_processes | 10 | Sim |
| critic | echo, get_current_time | 5 | Não |
| custom | Especificado pelo usuário | 10 | Não |

### GoalEngine
Gerencia objetivos de alto nível:

```python
from core.goal.engine import get_goal_engine

engine = get_goal_engine()

# Criar goal
goal = await engine.create_goal(
    objective="Pesquisar e comparar frameworks",
    success_criteria=["Encontrar top 3", "Comparar features"],
)

# Iniciar com plano
await engine.start_goal(goal.goal_id, plan_id="plan-123")

# Completar
await engine.complete_goal(goal.goal_id, result="Pesquisa concluída")

# Replanejar quando step falha
decision = await engine.request_replan(goal.goal_id, "step-2", "Tool failed")
```
