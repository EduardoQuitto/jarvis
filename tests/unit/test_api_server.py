"""Unit and integration tests for FastAPI Server endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from server.app import create_app
from core.config import get_settings


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def auth_headers():
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.mark.asyncio
async def test_health_endpoint_unauthorized(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_authorized(app, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["node_id"] == "node2-dev"
        assert data["registered_tools_count"] > 0
        assert "cpu" in data["system"]


@pytest.mark.asyncio
async def test_telemetry_endpoint(app, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/telemetry", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cpu" in data
        assert "memory" in data
        assert "disks" in data


@pytest.mark.asyncio
async def test_list_tools_endpoint(app, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tools", headers=auth_headers)
        assert response.status_code == 200
        tools = response.json()
        tool_names = [t["name"] for t in tools]
        assert "echo" in tool_names
        assert "get_system_metrics" in tool_names
        assert "launch_application" in tool_names


@pytest.mark.asyncio
async def test_execute_tool_green(app, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "tool_name": "echo",
            "parameters": {"message": "API test"},
            "confirmed": False,
        }
        response = await client.post("/tools/execute", json=payload, headers=auth_headers)
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["data"] == {"echo": "API test"}
        assert res_data["security_level"] == "GREEN"


@pytest.mark.asyncio
async def test_execute_tool_yellow_denied_without_confirmation(app, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "tool_name": "launch_application",
            "parameters": {"app_name": "notepad"},
            "confirmed": False,
        }
        response = await client.post("/tools/execute", json=payload, headers=auth_headers)
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["success"] is False
        assert "requires user confirmation" in res_data["error"]
        assert res_data["security_level"] == "YELLOW"
