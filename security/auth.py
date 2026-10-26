"""Authentication and authorization utilities for inter-node communication."""

import hmac
from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import TrustedDeviceConfig, get_settings

security_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class DeviceIdentity:
    """Authenticated device identity derived from the SERVER-side registry."""

    device_id: str
    descriptor: TrustedDeviceConfig


def resolve_trusted_device(token: Optional[str]) -> Optional[DeviceIdentity]:
    """Resolve an individual device token without leaking the token itself."""
    if not token:
        return None
    provided = token.strip()
    if not provided:
        return None

    match: Optional[DeviceIdentity] = None
    for device_id, descriptor in get_settings().trusted_devices.items():
        expected = descriptor.token.get_secret_value()
        if hmac.compare_digest(provided, expected):
            if match is not None:
                return None
            match = DeviceIdentity(device_id=device_id, descriptor=descriptor)
    return match


def verify_api_key(provided_key: Optional[str]) -> bool:
    """Compare provided key against configured API key using constant-time comparison."""
    if not provided_key:
        return False
    expected_key = get_settings().api_key
    return hmac.compare_digest(provided_key.strip(), expected_key.strip())


async def require_node_auth(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> str:
    """FastAPI dependency to enforce Bearer token / API key authentication."""
    if not credentials or not verify_api_key(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing node authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def require_device_identity(
    x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
    _node_token: str = Depends(require_node_auth),
) -> DeviceIdentity:
    """Enforce node auth plus an individually provisioned device token."""
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing device authentication token",
        )
    identity = resolve_trusted_device(x_device_token)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown or invalid device token",
        )
    return identity


async def optional_node_auth(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> Optional[str]:
    """FastAPI dependency that enforces auth in production but allows unauthenticated access in development.

    In development mode, returns None if no credentials provided.
    In production mode, behaves identically to require_node_auth.
    """
    settings = get_settings()
    if not settings.is_production:
        if credentials and verify_api_key(credentials.credentials):
            return credentials.credentials
        return None
    return await require_node_auth(credentials=credentials)
