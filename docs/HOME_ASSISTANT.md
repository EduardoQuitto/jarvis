# J.A.R.V.I.S. — Integração Home Assistant (Fase 15)

## Arquitetura

```text
Usuário
  ↓
CORE / Orchestrator (LLM interpreta a intenção)
  ↓
remote_server_tool (única ponte — sem bridge nova)
  ↓
SERVER ToolRegistry + PolicyEngine
  ↓
HomeAssistantClient (`core/home_assistant/`)
  ↓
Home Assistant → dispositivo / automação / cena / script
```

> **Home Assistant token = somente SERVER.** O CORE nunca recebe, armazena ou
> transmite o token. O CORE enxerga apenas os tools SHARED executados
> remotamente; a execução real sempre acontece no SERVER.

O J.A.R.V.I.S. é a camada inteligente sobre o Home Assistant: interpreta a
intenção, escolhe entidade/serviço e passa pela política existente. Ele NÃO
substitui o motor de automação (automations, scripts, scenes, triggers) e
NÃO cria scheduler próprio.

## Instalação do Home Assistant

Qualquer instalação com a HTTP API habilitada serve (HA OS, Container ou
Core). Anote o endereço LAN do servidor, por exemplo
`http://192.168.0.13:8123` (pode coexistir na mesma máquina do JARVIS SERVER,
emContainer Docker separado — sem dependências novas no repo).

## Configuração

### 1. Obter o Long-Lived Access Token

No frontend do Home Assistant: clique no seu usuário (canto inferior
esquerdo) → **Segurança** → **Tokens de acesso de longa duração** → **Criar
token**. Copie o valor uma única vez.

### 2. Onde colocar o token

**Somente no `.env` do SERVER** (Ubuntu). Nunca no CORE, nunca no Git:

```env
JARVIS_NODE_ROLE=SERVER
JARVIS_HOME_ASSISTANT_ENABLED=true
JARVIS_HOME_ASSISTANT_URL=http://192.168.0.13:8123
JARVIS_HOME_ASSISTANT_TOKEN=<token-somente-aqui>
JARVIS_HOME_ASSISTANT_TIMEOUT=10.0
```

O CORE mantém tudo desligado/desvazio para HA (o mecanismo de bridge o leva
ao SERVER automaticamente):

```env
JARVIS_NODE_ROLE=CORE
JARVIS_HOME_ASSISTANT_ENABLED=false
JARVIS_HOME_ASSISTANT_URL=
JARVIS_HOME_ASSISTANT_TOKEN=
```

### 3. Como o CORE acessa o HA

1. O SERVER registra `home_assistant_*` (SHARED) porque tem role SERVER +
   `home_assistant_enabled=true` + URL/token configurados.
2. O CORE lista esses tools via `remote_server_tool` (mesmo fluxo validado
   da ponte CORE ↔ SERVER).
3. Leituras (`get_state`, `get_states`) são GREEN e executam direto;
   atuações (`call_service`) são YELLOW e pedem confirmação como qualquer
   outra ação sensível.

## Ferramentas

| Tool | Nível | Uso |
|------|-------|-----|
| `home_assistant_get_state` | GREEN/SHARED | `{"entity_id": "light.sala"}` → estado + atributos |
| `home_assistant_get_states` | GREEN/SHARED | lista resumida (padrão 30, teto 100 entidades) |
| `home_assistant_call_service` | YELLOW/SHARED | `{"domain": "light", "service": "turn_on", "service_data": {...}}`; também `scene.turn_on`, `automation.trigger`, `script.turn_on`, `switch.*` |
| `home_assistant_wake_on_lan` | GREEN/SHARED | `{"mac": "AA:BB:CC:DD:EE:FF"}` via `wake_on_lan.send_magic_packet` (+ `broadcast_address`/`broadcast_port` opcionais) |

## Cenas, scripts e automações

Não crie YAML pelo J.A.R.V.I.S. nesta fase. Crie cenas/scripts/automações no
próprio Home Assistant e apenas **acione-os**:

- cena de cinema: `home_assistant_call_service {"domain": "scene", "service": "turn_on", "service_data": {"entity_id": "scene.cinema"}}`
- executar automação: `{"domain": "automation", "service": "trigger", ...}`
- rodar script: `{"domain": "script", "service": "turn_on", ...}`

## Wake-on-LAN

1. Habilite a integração `wake_on_lan` no Home Assistant.
2. Habilite WoL na BIOS/placa de rede da máquina alvo.
3. Use `home_assistant_wake_on_lan` com o MAC da máquina (ex.: o CORE).
4. O magic packet parte do host do Home Assistant — é ele o backbone da
   automação, não o CORE diretamente.

## Política de segurança

- Toda execução passa por `ToolRegistry.execute_tool()` + `PolicyEngine`
  (fronteira única, sem bypass).
- `domain`/`service`/`entity_id` validados como identificadores; `service_data`
  precisa ser objeto JSON (nunca string solta, nunca shell, nunca URL arbitrária).
- A URL do HA vem exclusivamente da configuração do SERVER.
- Token nunca aparece em logs, erros ou respostas (garantido por construção
  no `HomeAssistantClient` e coberto por teste).

## Como testar (sem HA real)

```bash
python -m pytest tests/unit/test_home_assistant.py -v   # tudo mockado
```

## Como testar (com HA real, manual)

```bash
python scripts/check_home_assistant.py            # health + versão
python scripts/check_home_assistant.py --states   # + leitura de estados
```

O script nunca exibe o token e retorna exit code ≠ 0 em falha.

## Troubleshooting

- `Home Assistant is not configured` → `JARVIS_HOME_ASSISTANT_ENABLED=true`
  + URL/token no `.env` **do SERVER**; tools só registram com role SERVER.
- `authentication failed (401)` → token inválido/expirado; gere outro no perfil.
- `connection refused` → URL errada ou HA fora do ar; confira IP/porta na LAN.
- `not found (404)` → `entity_id` inexistente (veja em Ferramentas de desenvolvedor → Estados).
- `rate limit (429)` → muitas chamadas; aguarde e tente de novo.
- CORE diz que o tool "não existe" → confira se o SERVER tem role + HA habilitado; o CORE só enxerga via `remote_server_tool`.
