"""Ollama LLM Provider — connects to Ollama's OpenAI-compatible API via httpx."""

import json
import asyncio
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
    RawToolCallDelta,
    StreamChunk,
)
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("jarvis.llm.ollama")


class OllamaProvider(BaseLLMProvider):
    """LLM provider that communicates with Ollama via its OpenAI-compatible endpoint.

    Requires Ollama running on the configured host/port (default: localhost:11434).
    Supports both generation and streaming with structured tool calling.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ):
        settings = get_settings()
        raw_url = base_url or settings.llm_base_url
        self.base_url = raw_url.rstrip("/") + "/v1"
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key or "ollama"
        self.timeout = timeout

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _messages_to_dicts(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage models to API-compatible dicts."""
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
                            "arguments": json.dumps(tc.function.arguments),
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
        """Convert LLMToolDef models to API-compatible dicts."""
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
        """Parse a non-streaming Ollama/OpenAI response into LLMResponse."""
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
        """Generate a complete response from Ollama."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._messages_to_dicts(messages),
            "stream": False,
            "temperature": temperature,
            "reasoning_effort": "none",
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
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg="Ollama is not reachable",
            )
        except httpx.HTTPStatusError as e:
            logger.error("Ollama HTTP error %s: %s", e.response.status_code, e.response.text[:200])
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg=f"Ollama HTTP error: {e.response.status_code}",
            )
        except Exception as e:
            logger.error("Ollama generation error: %s", str(e))
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg=f"Ollama error: {str(e)}",
            )

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response from Ollama chunk by chunk."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._messages_to_dicts(messages),
            "stream": True,
            "temperature": temperature,
            "reasoning_effort": "none",
        }

        tools_dicts = self._tools_to_dicts(tools)
        if tools_dicts:
            payload["tools"] = tools_dicts

        if max_tokens:
            payload["max_tokens"] = max_tokens
        # NOTE: transport/streaming failures propagate to the caller (the
        # router falls back or the orchestrator reports ERROR+DONE). They are
        # deliberately NOT converted into a fake successful stop chunk here:
        # that used to blind the router into record_success() with no real
        # response. Only malformed single SSE lines are skipped below.
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
                    except json.JSONDecodeError:
                        continue
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish = choice.get("finish_reason")

                    # Raw fragments only: argument JSON often arrives split
                    # across chunks, and parsing a fragment here would
                    # silently discard it. Parsing happens once the
                    # turn ends (see _StreamTurnAccumulator).
                    tool_calls_raw = []
                    for tc in delta.get("tool_calls", []):
                        func = tc.get("function", {})
                        args_raw = func.get("arguments", "")
                        if not isinstance(args_raw, str):
                            args_raw = json.dumps(args_raw)
                        tool_calls_raw.append(
                            RawToolCallDelta(
                                id=tc.get("id", ""),
                                type=tc.get("type", "function"),
                                name=func.get("name", ""),
                                arguments_str=args_raw,
                            )
                        )

                    yield StreamChunk(
                        content_delta=content,
                        tool_calls_raw=tool_calls_raw,
                        finish_reason=finish,
                    )

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            tags_url = self.base_url.replace("/v1", "") + "/api/tags"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(tags_url)
                return resp.status_code == 200
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Return configuration info about the model."""
        return {
            "provider": "ollama",
            "model": self.model,
            "base_url": self.base_url,
        }
