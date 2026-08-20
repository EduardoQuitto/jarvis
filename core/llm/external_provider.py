"""External LLM Provider — connects to any OpenAI-compatible API via httpx.

Supports Groq, Together AI, OpenRouter, Google Gemini, and any other
provider that implements the OpenAI /v1/chat/completions format.
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from core.contracts.llm import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDef,
    LLMFunctionCall,
    LLMUsage,
    StreamChunk,
)
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("jarvis.llm.external")


class ExternalProvider(BaseLLMProvider):
    """LLM provider that communicates with any OpenAI-compatible API.

    Works with Groq, Together AI, OpenRouter, Google Gemini, and any
    provider that exposes a /v1/chat/completions endpoint.

    Configuration via environment variables:
        JARVIS_EXTERNAL_LLM_API_KEY  — API key for the provider
        JARVIS_EXTERNAL_LLM_BASE_URL — API base URL (e.g. https://api.groq.com/openai/v1)
        JARVIS_EXTERNAL_LLM_MODEL    — Model name (e.g. llama-3.1-8b-instant)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        provider_name: str = "external",
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.external_llm_base_url).rstrip("/")
        self.model = model or settings.external_llm_model
        self.api_key = api_key or settings.external_llm_api_key
        self.timeout = timeout
        self._provider_name = provider_name or settings.external_llm_provider or "external"

        if not self.base_url:
            logger.warning("ExternalProvider: no base_url configured")
        if not self.api_key:
            logger.warning("ExternalProvider: no api_key configured")

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _messages_to_dicts(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        result = []
        for msg in messages:
            d: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.dumps(tc.function.arguments)
                            if isinstance(tc.function.arguments, dict)
                            else tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            if msg.name:
                d["name"] = msg.name
            result.append(d)
        return result

    def _tools_to_dicts(self, tools: Optional[List[LLMToolDef]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        return [
            {
                "type": t.type,
                "function": {
                    "name": t.function.name,
                    "description": t.function.description,
                    "parameters": t.function.parameters,
                },
            }
            for t in tools
        ]

    def _parse_response(self, data: Dict[str, Any]) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            args_raw = func.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                LLMToolCall(
                    id=tc.get("id", ""),
                    type=tc.get("type", "function"),
                    function=LLMFunctionCall(name=func.get("name", ""), arguments=args),
                )
            )

        usage_data = data.get("usage")
        usage = None
        if usage_data:
            usage = LLMUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
            model=data.get("model", self.model),
        )

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        if not self.base_url:
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg="External provider not configured: no base_url set",
            )

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._messages_to_dicts(messages),
            "temperature": temperature,
        }
        tools_dicts = self._tools_to_dicts(tools)
        if tools_dicts:
            payload["tools"] = tools_dicts
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._build_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except httpx.ConnectError:
            logger.error("Cannot connect to external provider at %s", self.base_url)
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg=f"External provider not reachable: {self.base_url}",
            )
        except httpx.HTTPStatusError as e:
            logger.error("External provider HTTP error %s: %s", e.response.status_code, e.response.text[:200])
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg=f"External provider HTTP error: {e.response.status_code}",
            )
        except Exception as e:
            logger.error("External provider error: %s", str(e))
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg=f"External provider error: {str(e)}",
            )

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        if not self.base_url:
            yield StreamChunk(content_delta="", finish_reason="stop")
            return

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._messages_to_dicts(messages),
            "stream": True,
            "temperature": temperature,
        }
        tools_dicts = self._tools_to_dicts(tools)
        if tools_dicts:
            payload["tools"] = tools_dicts
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._build_headers(),
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            yield StreamChunk(content_delta="", finish_reason="stop")
                            return
                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            finish = choice.get("finish_reason")

                            tool_calls_delta = []
                            for tc in delta.get("tool_calls", []):
                                func = tc.get("function", {})
                                args_raw = func.get("arguments", "{}")
                                try:
                                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                                except json.JSONDecodeError:
                                    args = {}
                                tool_calls_delta.append(
                                    LLMToolCall(
                                        id=tc.get("id", ""),
                                        type=tc.get("type", "function"),
                                        function=LLMFunctionCall(
                                            name=func.get("name", ""),
                                            arguments=args,
                                        ),
                                    )
                                )

                            yield StreamChunk(
                                content_delta=content,
                                tool_calls_deltas=tool_calls_delta,
                                finish_reason=finish,
                            )
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("External provider streaming error: %s", str(e))
            yield StreamChunk(content_delta="", finish_reason="stop")

    async def health_check(self) -> bool:
        if not self.base_url or not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._build_headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self._provider_name,
            "model": self.model,
            "base_url": self.base_url,
        }
