# J.A.R.V.I.S. — Camada de Memória e Persistência

## 1. Visão Geral

A primeira camada de persistência do J.A.R.V.I.S. é implementada sobre **SQLite assíncrono** (`aiosqlite`), garantindo que o sistema funcione com baixíssimo consumo de recursos (adequado ao Pentium G3260 e ao futuro i3-3220).

Bancos vetoriais e busca semântica pesada só serão integrados nas fases dedicadas do JARVIS Core (i5-14400).

---

## 2. Tabelas e Esquema Relacional

### `memory_store` (Armazenamento Chave-Valor Estruturado)
Armazena configurações, estados e preferências com suporte a namespaces por categoria:
* `key` (TEXT PRIMARY KEY): Chave única identificadora.
* `value` (TEXT NOT NULL): Objeto JSON serializado.
* `category` (TEXT NOT NULL DEFAULT 'general'): Escopo (ex: `preferences`, `system`, `workspace`).
* `updated_at` (TEXT NOT NULL): Timestamp UTC da última modificação.

### `audit_logs` (Trilha de Auditoria de Ações)
Registra todas as ferramentas executadas pelo sistema ou pelo usuário:
* `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
* `timestamp` (TEXT NOT NULL): Data e hora UTC.
* `node_id` (TEXT NOT NULL): Identificador do nó onde a ação correu.
* `tool_name` (TEXT NOT NULL): Nome da ferramenta executada.
* `security_level` (TEXT NOT NULL): Nível de segurança (`GREEN`, `YELLOW`, `RED`).
* `parameters` (TEXT NOT NULL): Parâmetros JSON enviados para a ferramenta.
* `success` (INTEGER NOT NULL): 1 para sucesso, 0 para falha.
* `error` (TEXT): Mensagem de erro em caso de falha.
* `duration_ms` (REAL NOT NULL): Tempo de execução em milissegundos.
