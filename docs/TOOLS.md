# J.A.R.V.I.S. — Sistema de Ferramentas (Tool System)

## 1. Estrutura do Sistema

O sistema de ferramentas fornece uma interface tipada, assíncrona e segura para execução de ações no sistema operacional e nós da rede.

```python
class BaseTool(ABC):
    name: str
    description: str
    security_level: SecurityLevel
    args_schema: Optional[Type[BaseModel]]
    timeout_seconds: float

    async def execute(self, **kwargs: Any) -> ToolResult:
        pass
```

---

## 2. Ferramentas Built-in Disponíveis

### `get_system_metrics` (🟢 GREEN)
* **Descrição:** Coleta dados reais de hardware sem estimativas ou alucinações (Regra da Fonte da Verdade).
* **Parâmetros:** Nenhum.
* **Retorno:** `SystemMetrics` (CPU percent, núcleos, frequência, RAM total/usada, partições de disco, uptime e top processos).

### `list_processes` (🟢 GREEN)
* **Descrição:** Lista processos ativos no sistema com consumo de CPU e memória.
* **Parâmetros:** `limit: int` (padrão 20), `sort_by: str` (memory, cpu, name).
* **Retorno:** Lista de `ProcessInfo` e total de processos ativos.

### `launch_application` (🟡 YELLOW)
* **Descrição:** Inicia uma aplicação aprovada na allowlist do sistema de segurança.
* **Parâmetros:** `app_name: str` (alias aprovado, ex: `notepad`, `calc`, `vscode`, `unity`).
* **Segurança:** Requer confirmação prévia (`confirmed=True`).

### `close_application` (🟡 YELLOW)
* **Descrição:** Encerra instâncias ativas de uma aplicação permitida na allowlist.
* **Parâmetros:** `app_name: str`.
* **Segurança:** Requer confirmação prévia (`confirmed=True`).

### `echo` (🟢 GREEN)
* **Descrição:** Ferramenta diagnóstica para teste de conectividade e validação do pipeline.
* **Parâmetros:** `message: str`.
