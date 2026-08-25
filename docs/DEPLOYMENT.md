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
