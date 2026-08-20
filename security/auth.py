"""Authentication and authorization utilities for inter-node communication."""

import hmac
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings

security_bearer = HTTPBearer(auto_error=False)


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
