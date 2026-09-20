"""Tests for the Google AI Studio (Gemini) cloud slot.

The Google slot reuses ExternalProvider (no dedicated class). Ollama stays
primary (priority 10, local); Google is fallback (priority 7, non-local);
mock stays last (priority 1). No test touches the real Google API — all
HTTP is mocked, and no real API key ever appears here.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.config import Settings, get_settings, reset_settings
from core.llm.external_provider import ExternalProvider
from core.llm.factory import create_llm_provider, create_router
from core.llm.mock_provider import MockLLMProvider
from core.llm.router import IntelligenceRouter
from core.contracts.llm import LLMMessage, LLMResponse


# --- 1. Settings ---

def test_google_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.google_model == "gemini-3.7-flash"
    assert settings.google_base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert settings.google_api_key == ""


def test_google_api_key_loads_from_environment(monkeypatch):
    monkeypatch.setenv("JARVIS_GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("JARVIS_GOOGLE_MODEL", "gemini-3.7-flash")
    reset_settings()
    settings = get_settings()
    assert settings.google_api_key == "test-google-key"
    assert settings.google_model == "gemini-3.7-flash"


# --- 2. Factory ---

def test_create_llm_provider_google(monkeypatch):
    monkeypatch.setenv("JARVIS_GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("JARVIS_GOOGLE_MODEL", "gemini-3.7-flash")
    monkeypatch.setenv("JARVIS_GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    reset_settings()
    provider = create_llm_provider("google")
    assert isinstance(provider, ExternalProvider)
    assert provider.provider_name == "google"
    assert provider.model == "gemini-3.7-flash"
    # ExternalProvider normalizes the trailing slash (matches existing behavior)
    assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert provider.api_key == "test-google-key"


def test_create_llm_provider_google_explicit_kwargs():
    provider = create_llm_provider(
        "google",
        base_url="https://example.com/v1/",
        model="test-model",
        api_key="k",
    )
    assert isinstance(provider, ExternalProvider)
    assert provider.provider_name == "google"
    assert provider.base_url == "https://example.com/v1"
    assert provider.model == "test-model"


# --- 3. Router registration & ordering ---

def _google_env(monkeypatch):
    monkeypatch.setenv("JARVIS_GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("JARVIS_GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    monkeypatch.setenv("JARVIS_GOOGLE_MODEL", "gemini-3.7-flash")
    reset_settings()


def test_router_registers_google_between_ollama_and_mock(monkeypatch):
    _google_env(monkeypatch)
    router = create_router()
    entries = {e.name: e for e in router._registry.list_providers()}
    assert set(entries) == {"ollama", "google", "mock"}
    assert entries["ollama"].priority > entries["google"].priority > entries["mock"].priority
    assert entries["ollama"].priority == 10.0
    assert entries["google"].priority == 7.0
    assert entries["mock"].priority == 1.0
    assert entries["ollama"].local is True
    assert entries["google"].local is False


def test_router_skips_google_without_api_key(monkeypatch):
    # conftest already clears the key; base URL default alone must not enable it
    reset_settings()
    router = create_router()
    names = {e.name for e in router._registry.list_providers()}
    assert "google" not in names
    assert names == {"ollama", "mock"}


# --- 4. Fallback: ollama error -> google answers (no real network) ---

def _mock_chat_response(content="Hello from Gemini!"):
    # Same pattern as tests/unit/test_external_provider.py: sync MagicMock
    # for status/json/raise_for_status (httpx responses are not awaitable).
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "model": "gemini-3.7-flash",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.asyncio
async def test_router_falls_back_to_google(monkeypatch):
    _google_env(monkeypatch)
    router = create_router()

    entries = {e.name: e for e in router._registry.list_providers()}
    ollama_entry = entries["ollama"]
    google_entry = entries["google"]

    # Ollama fails; Google answers through mocked HTTP
    monkeypatch.setattr(ollama_entry.provider, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        ollama_entry.provider, "generate",
        AsyncMock(return_value=LLMResponse(content=None, tool_calls=[], finish_reason="stop",
                                           error_msg="Ollama is not reachable")),
    )
    monkeypatch.setattr(google_entry.provider, "health_check", AsyncMock(return_value=True))
    with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_chat_response())

        with patch("core.llm.mock_provider.MockLLMProvider.health_check", AsyncMock(return_value=True)):
            response = await router.route(messages=[LLMMessage(role="user", content="Hi")])

    assert response.error_msg is None
    assert response.content == "Hello from Gemini!"
    assert response.model == "gemini-3.7-flash"


# --- 5. Visibility: Google is non-local, sees only SHARED tools ---

@pytest.mark.asyncio
async def test_google_is_non_local_next_provider(monkeypatch):
    _google_env(monkeypatch)
    router = create_router()
    entries = {e.name: e for e in router._registry.list_providers()}

    # Ollama unhealthy -> Google is next
    monkeypatch.setattr(entries["ollama"].provider, "health_check", AsyncMock(return_value=False))
    monkeypatch.setattr(entries["google"].provider, "health_check", AsyncMock(return_value=True))
    with patch("core.llm.mock_provider.MockLLMProvider.health_check", AsyncMock(return_value=False)):
        assert await router.is_next_provider_local() is False

    assert entries["google"].local is False


# --- 6. ExternalProvider pointed at Google (unit, mocked HTTP) ---

@pytest.mark.asyncio
async def test_external_provider_works_with_google_base_url():
    provider = ExternalProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.7-flash",
        api_key="test-google-key",
        provider_name="google",
    )
    assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert provider.provider_name == "google"

    with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_chat_response("OK"))

        response = await provider.generate(messages=[LLMMessage(role="user", content="Hi")])

    assert response.error_msg is None
    assert response.content == "OK"
    # The API key travels only in the Authorization header, never in URL/payload
    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer test-google-key"
    assert "test-google-key" not in str(kwargs["json"])
    assert "generativelanguage" not in str(kwargs["json"])
