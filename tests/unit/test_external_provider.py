"""Tests for ExternalProvider — OpenAI-compatible external LLM provider."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from core.llm.external_provider import ExternalProvider
from core.contracts.llm import LLMMessage, LLMResponse, LLMToolCall, LLMFunctionCall, LLMToolDef, LLMFunctionSchema


def _mock_httpx_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        mock_request = MagicMock(spec=Request)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = status_code
        mock_response.text = json.dumps(json_data) if json_data else ""
        resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"HTTP {status_code}",
            request=mock_request,
            response=mock_response,
        )
    return resp


class TestExternalProviderInit:
    def test_init_with_explicit_params(self):
        p = ExternalProvider(
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.1-8b-instant",
            api_key="test-key",
            provider_name="groq",
        )
        assert p.base_url == "https://api.groq.com/openai/v1"
        assert p.model == "llama-3.1-8b-instant"
        assert p.api_key == "test-key"
        assert p._provider_name == "groq"

    def test_init_strips_trailing_slash(self):
        p = ExternalProvider(
            base_url="https://api.example.com/v1/",
            api_key="k",
            model="m",
        )
        assert p.base_url == "https://api.example.com/v1"

    def test_init_uses_settings_defaults(self):
        with patch("core.llm.external_provider.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                external_llm_base_url="https://api.test.com/v1",
                external_llm_model="test-model",
                external_llm_api_key="test-key",
                external_llm_provider="test",
            )
            p = ExternalProvider()
            assert p.base_url == "https://api.test.com/v1"
            assert p.model == "test-model"


class TestExternalProviderGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        p = ExternalProvider(
            base_url="https://api.test.com/v1",
            model="test-model",
            api_key="test-key",
        )

        mock_response_data = {
            "model": "test-model",
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, mock_response_data))

            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])

            assert response.content == "Hello!"
            assert response.error_msg is None
            assert response.model == "test-model"
            assert response.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_generate_no_base_url(self):
        p = ExternalProvider(base_url="", api_key="k", model="m")
        response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
        assert response.error_msg is not None
        assert "not configured" in response.error_msg

    @pytest.mark.asyncio
    async def test_generate_connection_error(self):
        p = ExternalProvider(
            base_url="https://api.test.com/v1",
            model="m",
            api_key="k",
        )

        import httpx
        with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

            response = await p.generate(messages=[LLMMessage(role="user", content="Hi")])
            assert response.error_msg is not None
            assert "not reachable" in response.error_msg

    @pytest.mark.asyncio
    async def test_generate_tool_calls(self):
        p = ExternalProvider(
            base_url="https://api.test.com/v1",
            model="m",
            api_key="k",
        )

        mock_response_data = {
            "model": "m",
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-001",
                        "type": "function",
                        "function": {"name": "echo", "arguments": '{"message": "hi"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }

        with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, mock_response_data))

            response = await p.generate(messages=[LLMMessage(role="user", content="Echo")])
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].function.name == "echo"
            assert response.tool_calls[0].function.arguments == {"message": "hi"}


class TestExternalProviderHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        p = ExternalProvider(base_url="https://api.test.com/v1", api_key="k", model="m")
        with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_httpx_response(200))
            assert await p.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_no_config(self):
        p = ExternalProvider(base_url="", api_key="", model="m")
        assert await p.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_connection_failure(self):
        p = ExternalProvider(base_url="https://api.test.com/v1", api_key="k", model="m")
        import httpx
        with patch("core.llm.external_provider.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("nope"))
            assert await p.health_check() is False


class TestExternalProviderModelInfo:
    def test_get_model_info(self):
        p = ExternalProvider(
            base_url="https://api.test.com/v1",
            model="llama-3",
            api_key="k",
            provider_name="groq",
        )
        info = p.get_model_info()
        assert info["provider"] == "groq"
        assert info["model"] == "llama-3"
        assert info["base_url"] == "https://api.test.com/v1"
