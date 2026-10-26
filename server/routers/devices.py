"""Devices API Router — /api/devices endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import endpoint_host_port
from core.device.registry import DeviceRegistry
from core.contracts.device import (
    DeviceRegistrationRequest,
    DeviceHeartbeat,
    DeviceType,
    NodeStatus,
)
from core.logger import get_logger
from security.auth import DeviceIdentity, require_device_identity, require_node_auth

logger = get_logger("jarvis.api.devices")

router = APIRouter(prefix="/api/devices", tags=["devices"])

_registry: Optional[DeviceRegistry] = None


def _get_registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
    return _registry


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., description="Unique device ID")
    name: str = Field(default="", description="Device name")
    device_type: str = Field(default="UNKNOWN", description="Device type")
    capabilities: List[str] = Field(default_factory=list, description="Device capabilities")
    version: str = Field(default="0.1.0", description="Software version")
    ip_address: Optional[str] = None
    port: Optional[int] = None


class HeartbeatRequest(BaseModel):
    device_id: str
    status: str = Field(default="ONLINE")
    memory_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    network_latency: Optional[float] = None
    capabilities: List[str] = Field(default_factory=list)


@router.post("/", response_model=Dict[str, Any])
async def register_device(
    request: DeviceRegisterRequest,
    identity: DeviceIdentity = Depends(require_device_identity),
) -> Dict[str, Any]:
    """Register the authenticated device using its SERVER-side descriptor."""
    if request.device_id != identity.device_id:
        raise HTTPException(
            status_code=403,
            detail="device_id does not match authenticated device",
        )

    try:
        registry = _get_registry()
        descriptor = identity.descriptor
        host, port = endpoint_host_port(descriptor.endpoint)
        req = DeviceRegistrationRequest(
            device_id=identity.device_id,
            name=request.name,
            device_type=descriptor.device_type,
            capabilities=list(descriptor.capabilities),
            version=request.version,
            ip_address=host,
            port=port,
        )
        device = await registry.register_device(req)
        return {
            "device_id": device.device_id,
            "status": device.status.value,
            "registered": True,
        }
    except Exception as e:
        logger.error("Register device error: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error during device registration.")


@router.post("/heartbeat")
async def send_heartbeat(
    request: HeartbeatRequest,
    identity: DeviceIdentity = Depends(require_device_identity),
) -> Dict[str, Any]:
    """Send a heartbeat for the authenticated device only."""
    if request.device_id != identity.device_id:
        raise HTTPException(
            status_code=403,
            detail="device_id does not match authenticated device",
        )

    try:
        registry = _get_registry()
        try:
            status = NodeStatus(request.status)
        except ValueError:
            status = NodeStatus.ONLINE

        heartbeat = DeviceHeartbeat(
            device_id=identity.device_id,
            status=status,
            capabilities=[],
        )
        await registry.update_heartbeat(heartbeat)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Heartbeat error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[Dict[str, Any]])
async def list_devices(
    device_type: Optional[str] = None,
    _token: str = Depends(require_node_auth),
) -> List[Dict[str, Any]]:
    """List all devices."""
    try:
        registry = _get_registry()
        dt = DeviceType(device_type) if device_type else None
        devices = await registry.list_devices(device_type=dt)
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "device_type": d.device_type.value,
                "status": d.status.value,
                "capabilities": [c.value if hasattr(c, 'value') else c for c in d.capabilities],
                "version": d.version,
                "ip_address": d.ip_address,
                "port": d.port,
                "last_seen": d.last_seen.isoformat() if hasattr(d.last_seen, 'isoformat') else str(d.last_seen),
            }
            for d in devices
        ]
    except Exception as e:
        logger.error("List devices error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/online", response_model=List[Dict[str, Any]])
async def list_online_devices(
    _token: str = Depends(require_node_auth),
) -> List[Dict[str, Any]]:
    """List all online devices."""
    try:
        registry = _get_registry()
        devices = await registry.get_online_devices()
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "device_type": d.device_type.value,
                "status": d.status.value,
                "capabilities": [c.value if hasattr(c, 'value') else c for c in d.capabilities],
                "ip_address": d.ip_address,
                "port": d.port,
            }
            for d in devices
        ]
    except Exception as e:
        logger.error("Online devices error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def device_summary(
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Get device capability summary."""
    try:
        from core.device.router import CapabilityRouter
        router = CapabilityRouter(registry=_get_registry())
        return await router.get_status_summary()
    except Exception as e:
        logger.error("Device summary error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}")
async def remove_device(
    device_id: str,
    _token: str = Depends(require_node_auth),
) -> Dict[str, Any]:
    """Remove a device from the registry."""
    try:
        registry = _get_registry()
        await registry.remove_device(device_id)
        return {"status": "removed", "device_id": device_id}
    except Exception as e:
        logger.error("Remove device error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
