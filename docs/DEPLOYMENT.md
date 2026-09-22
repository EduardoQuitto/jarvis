# J.A.R.V.I.S. — Deployment Guide

## Running the Server

### Development Mode

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1    # Windows PowerShell
source .venv/bin/activate        # Linux/macOS

# Start with auto-reload
python -m uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

The server will be available at `http://127.0.0.1:8000`.

### Production Mode

```bash
# Start without auto-reload, bind to all interfaces
python -m uvicorn server.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
```

> **Note:** Production security features (CORS hardening, rate limiting, API key rotation) are planned for Phase 12 and not yet implemented.

## CLI Commands

JARVIS provides a CLI for common operations:

```bash
# Show node status and telemetry
python -m core.cli status

# List registered tools
python -m core.cli tools

# Run a sample diagnostic plan
python -m core.cli test-plan

# Start the server (alternative to uvicorn)
python -m core.cli server
```

## Environment Variables

All configuration is managed via environment variables with the `JARVIS_` prefix. See `.env.example` for the full list.

Key variables for deployment:

| Variable | Purpose | Default |
|----------|---------|---------|
| `JARVIS_HOST` | Bind address | `127.0.0.1` |
| `JARVIS_PORT` | Bind port | `8000` |
| `JARVIS_API_KEY` | Authentication token | `jarvis-dev-insecure-key-change-me` |
| `JARVIS_ENV` | Environment mode | `development` |
| `JARVIS_LOG_LEVEL` | Logging verbosity | `INFO` |
| `JARVIS_DB_PATH` | SQLite database path | `./data/jarvis.db` |

## Health Check

```bash
curl http://127.0.0.1:8000/health -H "Authorization: Bearer YOUR_API_KEY"
```

## Running Tests Before Deployment

```bash
pytest -v    # Ensure all 230 tests pass
```

## Phase 12 Manual Checklist (Ubuntu SERVER + Windows CORE)

No remote deploy is automated. With the Ubuntu SERVER on, configure manually:

**SERVER `.env` (Ubuntu, never leaves the machine):**
```env
JARVIS_NODE_ID=jarvis-server
JARVIS_NODE_ROLE=SERVER
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8000
JARVIS_API_KEY=<shared-node-key>
JARVIS_GOOGLE_API_KEY=<gemini-key-only-here>
JARVIS_GOOGLE_MODEL=gemini-3.7-flash
JARVIS_GOOGLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
JARVIS_DB_PATH=./data/jarvis.db
```

**CORE `.env` (Windows, no Gemini key here):**
```env
JARVIS_NODE_ID=jarvis-core
JARVIS_NODE_ROLE=CORE
JARVIS_SERVER_URL=http://192.168.0.13:8000
JARVIS_SERVER_API_KEY=<same-shared-node-key>
JARVIS_CENTRAL_STATE_ENABLED=true
# Cloud slot routed THROUGH the SERVER relay (node key, not the Gemini key):
JARVIS_GOOGLE_BASE_URL=http://192.168.0.13:8000/api/llm
JARVIS_GOOGLE_API_KEY=<same-shared-node-key>
JARVIS_GOOGLE_MODEL=gemini-3.7-flash
```

**Verify (from the CORE machine):**
```bash
python scripts/check_remote_server.py   # health/tools/echo on SERVER
python scripts/check_remote_tasks.py    # task lifecycle on SERVER
python scripts/check_google_provider.py # Gemini via SERVER relay
```

**External access (future, NOT implemented):** external client → secure
private network / VPN (future phase) → SERVER → CORE. Never expose JARVIS
directly to the public internet; no port-forwarding without VPN + auth.
