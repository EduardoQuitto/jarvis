"""LLM relay — SERVER-side Gemini access for compute nodes (/api/llm).

The Gemini API key lives ONLY on the SERVER (.env of the SERVER node).
Compute nodes (CORE) never receive or store it: they point their cloud
provider slot at this OpenAI-compatible relay, authenticating with the
shared node key like any other node-to-node call.

This router is a dumb, explicit relay: no prompt handling, no tool loop,
no fallback logic (those stay on the CORE router/provider). Upstream HTTP
statuses propagate so the CORE provider keeps its retry semantics.
"""

import asyncio
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import httpx

from core.config import get_settings
from core.logger import get_logger
from security.auth import require_node_auth

logger = get_logger("jarvis.api.llm_relay")

router = APIRouter(prefix="/api/llm", tags=["llm-relay"])


def _google_target() -> tuple:
    """Return (base_url, api_key) or raise explicit 503 when unconfigured."""
    settings = get_settings()
    base_url = (settings.google_base_url or "").rstrip("/")
    if not settings.google_api_key or not base_url:
        raise HTTPException(
            status_code=503,
            detail="Gemini is not configured on this SERVER (missing API key or base URL).",
        )
    return base_url, settings.google_api_key


def _google_headers(api_key: str) -> Dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}


@router.get("/models")
async def relay_models(_token: str = Depends(require_node_auth)):
    """Relay GET {google}/models (used as health check by cloud slots)."""
    base_url, api_key = _google_target()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/models", headers=_google_headers(api_key))
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail=f"Gemini endpoint timed out: {e}")
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise HTTPException(status_code=502, detail=f"Gemini endpoint unreachable: {e}")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Gemini endpoint error.")
    try:
        return response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Gemini endpoint returned invalid JSON.")


@router.post("/chat/completions")
async def relay_chat_completions(
    request: Request,
    _token: str = Depends(require_node_auth),
):
    """Relay an OpenAI-compatible chat request to Gemini (streaming or not)."""
    base_url, api_key = _google_target()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object.")
    timeout = get_settings().llm_timeout

    if body.get("stream"):
        async def _relay_stream():
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST", f"{base_url}/chat/completions",
                        headers=_google_headers(api_key), json=body,
                    ) as upstream:
                        if upstream.status_code >= 400:
                            raise HTTPException(
                                status_code=upstream.status_code,
                                detail="Gemini endpoint error.",
                            )
                        async for chunk in upstream.aiter_bytes():
                            yield chunk
            except HTTPException:
                raise
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException as e:
                raise HTTPException(status_code=504, detail=f"Gemini stream timed out: {e}")
            except (httpx.ConnectError, httpx.NetworkError) as e:
                raise HTTPException(status_code=502, detail=f"Gemini stream unreachable: {e}")

        return StreamingResponse(_relay_stream(), media_type="text/event-stream")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=_google_headers(api_key),
                json=body,
            )
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail=f"Gemini endpoint timed out: {e}")
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise HTTPException(status_code=502, detail=f"Gemini endpoint unreachable: {e}")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Gemini endpoint error.")
    try:
        return response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Gemini endpoint returned invalid JSON.")
