# J.A.R.V.I.S. — Personal Distributed Intelligence

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Architecture](https://img.shields.io/badge/architecture-modular%20%26%20distributed-green.svg)](#)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#)

J.A.R.V.I.S. é um assistente pessoal local, modular e distribuído, construído com foco em segurança, portabilidade e desacoplamento de hardware.

---

##  Arquitetura e Topologia

O sistema é planejado para operar em uma rede de nós heterogêneos:

* **JARVIS SERVER (i3-3220 / 8 GB / Ubuntu Server):** Gateway 24/7, Home Assistant, automações, scheduler, Wake-on-LAN.
* **JARVIS CORE (i5-14400 / 32 GB / NVMe):** Raciocínio, IA local, síntese/reconhecimento de voz, visão computacional.
* **NODE 2 / Windows Agent (i5-7400 / 8 GB / GTX 650 Ti):** Ambiente de desenvolvimento e nó auxiliar para tarefas nativas do Windows.
* **JARVIS MOBILE (Galaxy S20 FE):** Sensores móveis, notificações, controle Android.
* **JARVIS PANEL (Galaxy Tab E):** Dashboard de telemetria ultraleve.

---

##  Como Executar Localmente

### 1. Clonar e Configurar o Ambiente

```powershell
# Criar ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -e .
```

### 2. Configurar Variáveis de Ambiente

Copie o arquivo `.env.example` para `.env`:
```powershell
Copy-Item .env.example .env
```

### 3. Executar os Testes Automatizados

```powershell
pytest -v
```

### 4. Iniciar o Servidor do Nó

```powershell
python -m uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

---

##  Camada de Segurança

* **Classificação por Cores:**
  * 🟢 **Verde:** Consultas de telemetria e processos (execução imediata).
  * 🟡 **Amarelo:** Inicialização e encerramento de programas autorizados (requer confirmação).
  * 🔴 **Vermelho:** Alterações críticas de sistema ou exclusão de dados (autorização reforçada).
* **Sem Shell Arbitrário:** Comandos são restritos a ferramentas tipadas com verificação de *allowlist* e *path sandboxing*.
* **Fonte da Verdade:** O sistema nunca inventa estados ou métricas — tudo é lido diretamente do hardware em tempo real.

---

##  Documentação Técnica

Consulte o diretório [`docs/`](docs/) para especificações completas:
* [`docs/AGENTS.md`](docs/AGENTS.md) — Regras permanentes do projeto
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Arquitetura de software e contratos
* [`docs/SECURITY.md`](docs/SECURITY.md) — Modelo de segurança e políticas
* [`docs/TOOLS.md`](docs/TOOLS.md) — Sistema de ferramentas tipadas
* [`docs/API.md`](docs/API.md) — Especificação dos endpoints REST
* [`docs/MEMORY.md`](docs/MEMORY.md) — Camada de memória e persistência SQLite
* [`docs/ROADMAP.md`](docs/ROADMAP.md) — Roadmap de desenvolvimento
