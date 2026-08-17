"""Health and Telemetry API routes."""

from fastapi import APIRouter, Depends
from core.contracts.telemetry import SystemMetrics
from security.auth import require_node_auth
from server.schemas import HealthResponse
from windows_agent.system import WindowsSystemCollector
from tools.registry import get_tool_registry
from core.config import get_settings

router = APIRouter(prefix="", tags=["Health & Telemetry"])


@router.get("/health", response_model=HealthResponse)
async def get_node_health(_token: str = Depends(require_node_auth)):
    """Retrieve node health and hardware status."""
    settings = get_settings()
    registry = get_tool_registry()
    system_metrics = WindowsSystemCollector.collect(node_id=settings.node_id)
    gpu_info = WindowsSystemCollector.get_gpu_info()

    return HealthResponse(
        status="healthy",
        node_id=settings.node_id,
        node_role=settings.node_role.value,
        registered_tools_count=len(registry.list_tools()),
        system=system_metrics,
        gpu=gpu_info,
    )


@router.get("/telemetry", response_model=SystemMetrics)
async def get_node_telemetry(_token: str = Depends(require_node_auth)):
    """Retrieve detailed real-time hardware telemetry without estimation."""
    settings = get_settings()
    return WindowsSystemCollector.collect(node_id=settings.node_id)
