"""FastAPI Application factory and configuration."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from tools.registry import get_tool_registry
from tools import register_default_tools
from server.routers.health import router as health_router
from server.routers.system import router as system_router
from server.routers.tools import router as tools_router
from server.routers.chat import router as chat_router
from server.routers.tasks import router as tasks_router
from server.routers.devices import router as devices_router
from server.routers.memory import router as memory_router
from server.routers.mcp import router as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for startup and shutdown."""
    # Startup: Ensure default tools are registered
    registry = get_tool_registry()
    register_default_tools(registry)
    yield
    # Shutdown logic if needed


def create_app() -> FastAPI:
    """Create and configure FastAPI instance."""
    settings = get_settings()

    # Ensure default tools are registered
    registry = get_tool_registry()
    register_default_tools(registry)

    app = FastAPI(
        title="J.A.R.V.I.S. Node API",
        version="0.1.0",
        description="Distributed modular interface for JARVIS system and node automation.",
        debug=settings.debug,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(health_router)
    app.include_router(system_router)
    app.include_router(tools_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(devices_router)
    app.include_router(memory_router)
    app.include_router(mcp_router)

    return app
