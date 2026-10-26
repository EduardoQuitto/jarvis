"""Patch 1A: device identity, server-controlled descriptors, and route auth."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from core.config import Settings, TrustedDeviceConfig, get_settings, reset_settings
from server.app import create_app

TOKEN_A = "test-device-token-a-0123456789"
TOKEN_B = "test-device-token-b-0123456789"
CORE_ENDPOINT = "http://192.168.0.8:8000"
OTHER_ENDPOINT = "http://192.168.0.9:8000"


def _entry(token=TOKEN_A, endpoint=CORE_ENDPOINT, device_type="CORE", capabilities=None):
    return {
        "token": token,
        "device_type": device_type,
        "capabilities": capabilities or ["llm"],
        "endpoint": endpoint,
    }


def _configure(monkeypatch, devices=None, env="development"):
    monkeypatch.setenv("JARVIS_ENV", env)
    monkeypatch.setenv(
        "JARVIS_TRUSTED_DEVICES",
        json.dumps(devices if devices is not None else {
            "jarvis-core": _entry(),
            "jarvis-other": _entry(TOKEN_B, OTHER_ENDPOINT),
        }),
    )
    reset_settings()


def _node_headers():
    return {"Authorization": f"Bearer {get_settings().api_key}"}


def _device_headers(token=TOKEN_A):
    return {**_node_headers(), "X-Device-Token": token}


def _register_body(device_id="jarvis-core", **overrides):
    body = {
        "device_id": device_id,
        "name": "core",
        "device_type": "CORE",
        "capabilities": ["llm"],
        "version": "0.5.0",
    }
    body.update(overrides)
    return body


def _app_client():
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize("env", ["development", "production"])
async def test_device_routes_require_node_auth(monkeypatch, env):
    _configure(monkeypatch, env=env)
    async with _app_client() as client:
        assert (await client.post("/api/devices/", json=_register_body())).status_code == 401
        assert (await client.post(
            "/api/devices/heartbeat", json={"device_id": "jarvis-core"},
        )).status_code == 401
        assert (await client.get("/api/devices/")).status_code == 401
        assert (await client.get("/api/devices/online")).status_code == 401
        assert (await client.get("/api/devices/summary")).status_code == 401
        assert (await client.delete("/api/devices/jarvis-core")).status_code == 401


@pytest.mark.asyncio
async def test_invalid_node_or_device_credentials_do_not_write(monkeypatch):
    _configure(monkeypatch)
    async with _app_client() as client:
        invalid_node = await client.post(
            "/api/devices/", json=_register_body(),
            headers={"Authorization": "Bearer wrong", "X-Device-Token": TOKEN_A},
        )
        assert invalid_node.status_code == 401

        missing_device = await client.post(
            "/api/devices/", json=_register_body(), headers=_node_headers(),
        )
        assert missing_device.status_code == 401

        unknown_device = await client.post(
            "/api/devices/", json=_register_body(),
            headers=_device_headers("unknown-device-token-0123456789"),
        )
        assert unknown_device.status_code == 403

        devices = (await client.get("/api/devices/", headers=_node_headers())).json()
    assert devices == []


@pytest.mark.asyncio
async def test_device_a_cannot_register_or_heartbeat_device_b(monkeypatch):
    _configure(monkeypatch)
    async with _app_client() as client:
        registered_b = await client.post(
            "/api/devices/",
            json=_register_body("jarvis-other", name="other"),
            headers=_device_headers(TOKEN_B),
        )
        assert registered_b.status_code == 200

        forged = await client.post(
            "/api/devices/",
            json=_register_body("jarvis-other", name="forged"),
            headers=_device_headers(TOKEN_A),
        )
        assert forged.status_code == 403

        before = next(
            d for d in (await client.get("/api/devices/", headers=_node_headers())).json()
            if d["device_id"] == "jarvis-other"
        )
        assert before["name"] == "other"

        assert (await client.post(
            "/api/devices/heartbeat",
            json={"device_id": "jarvis-other", "status": "ERROR"},
            headers=_device_headers(TOKEN_A),
        )).status_code == 403

        after = next(
            d for d in (await client.get("/api/devices/", headers=_node_headers())).json()
            if d["device_id"] == "jarvis-other"
        )
    assert after["status"] == "ONLINE"
    assert after["last_seen"] == before["last_seen"]


@pytest.mark.asyncio
async def test_client_identity_fields_are_ignored(monkeypatch):
    _configure(monkeypatch)
    async with _app_client() as client:
        response = await client.post(
            "/api/devices/",
            json=_register_body(
                device_type="MOBILE",
                capabilities=["sensor"],
                ip_address="10.0.0.99",
                port=9999,
            ),
            headers=_device_headers(TOKEN_A),
        )
        assert response.status_code == 200

        device = (await client.get("/api/devices/", headers=_node_headers())).json()[0]
    assert device["device_type"] == "CORE"
    assert device["capabilities"] == ["llm"]
    assert device["ip_address"] == "192.168.0.8"
    assert device["port"] == 8000


@pytest.mark.asyncio
async def test_provisioned_core_can_register_and_heartbeat(monkeypatch):
    _configure(monkeypatch)
    async with _app_client() as client:
        assert (await client.post(
            "/api/devices/", json=_register_body(), headers=_device_headers(TOKEN_A),
        )).status_code == 200
        assert (await client.post(
            "/api/devices/heartbeat",
            json={"device_id": "jarvis-core", "status": "READY"},
            headers=_device_headers(TOKEN_A),
        )).status_code == 200
        device = (await client.get("/api/devices/", headers=_node_headers())).json()[0]
    assert device["device_id"] == "jarvis-core"
    assert device["device_type"] == "CORE"
    assert device["status"] == "READY"


@pytest.mark.parametrize("endpoint", [
    "ftp://192.168.0.8:8000",
    "http://user:pass@192.168.0.8:8000",
    "http://192.168.0.8:0",
    "http://192.168.0.8:70000",
    "http://192.168.0.8:8000/path",
    "http://192.168.0.8:8000?query=1",
    "http://192.168.0.8:8000#fragment",
    "http://",
    "not-a-url",
    "http://host\r:8000",
    "http://host\n:8000",
    "http://host\x00:8000",
    "http://host\t:8000",
])
def test_trusted_endpoint_rejects_invalid_values(endpoint):
    with pytest.raises(ValidationError):
        TrustedDeviceConfig(token=TOKEN_A, endpoint=endpoint)


def test_trusted_endpoint_is_normalized():
    descriptor = TrustedDeviceConfig(token=TOKEN_A, endpoint=f"{CORE_ENDPOINT}/")
    assert descriptor.endpoint == CORE_ENDPOINT


def test_trusted_devices_reject_duplicate_tokens():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_devices={
            "jarvis-core": TrustedDeviceConfig(token=TOKEN_A, endpoint=CORE_ENDPOINT),
            "jarvis-other": TrustedDeviceConfig(token=TOKEN_A, endpoint=OTHER_ENDPOINT),
        })


@pytest.mark.asyncio
async def test_register_device_exception_returns_generic_message(monkeypatch):
    _configure(monkeypatch)
    import server.routers.devices as dev_mod
    original_registry = dev_mod._get_registry

    class FailingRegistry:
        async def register_device(self, *args, **kwargs):
            raise RuntimeError("DB internal schema detail leak")

    monkeypatch.setattr(dev_mod, "_get_registry", lambda: FailingRegistry())
    async with _app_client() as client:
        response = await client.post(
            "/api/devices/",
            json=_register_body(),
            headers=_device_headers(),
        )
    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert "DB internal" not in detail
    assert "schema" not in detail
    assert "Internal server error" in detail
