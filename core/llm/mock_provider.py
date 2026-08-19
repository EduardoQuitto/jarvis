"""Mock LLM Provider for testing without a real model."""

import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

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
from core.logger import get_logger

logger = get_logger("jarvis.llm.mock")


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider that returns scripted responses for testing.

    Supports:
    - Cycling through a list of responses
    - Auto-generating tool calls for testing the agentic loop
    - Configurable response text
    - Health check simulation
    """

    def __init__(
        self,
        responses: Optional[List[LLMResponse]] = None,
        default_text: str = "I can help you with that. Let me check the system metrics.",
        auto_tool_calls: bool = False,
        healthy: bool = True,
    ):
        self._responses = responses or []
        self._call_index = 0
        self._default_text = default_text
        self._auto_tool_calls = auto_tool_calls
        self._healthy = healthy
        self._all_calls: List[Dict[str, Any]] = []

    def add_response(self, response: LLMResponse) -> None:
        """Add a response to the queue."""
        self._responses.append(response)

    def set_responses(self, responses: List[LLMResponse]) -> None:
        """Replace all queued responses."""
        self._responses = responses
        self._call_index = 0

    def get_all_calls(self) -> List[Dict[str, Any]]:
        """Return all calls made to this provider (for test assertions)."""
        return self._all_calls

    def _next_response(self) -> LLMResponse:
        """Get the next scripted response or generate a default."""
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp

        if self._auto_tool_calls and self._call_index == 0:
            self._call_index += 1
            return LLMResponse(
                content=None,
                tool_calls=[
                    LLMToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=LLMFunctionCall(
                            name="echo",
                            arguments={"message": "System check complete"},
                        ),
                    )
                ],
                finish_reason="tool_calls",
                model="mock-model",
            )

        self._call_index += 1
        return LLMResponse(
            content=self._default_text,
            tool_calls=[],
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            model="mock-model",
        )

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Return the next scripted response."""
        self._all_calls.append({
            "method": "generate",
            "messages_count": len(messages),
            "has_tools": tools is not None,
            "tools_count": len(tools) if tools else 0,
        })
        logger.debug("Mock LLM generate called (call #%d)", len(self._all_calls))
        return self._next_response()

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream the next scripted response as a single chunk."""
        self._all_calls.append({
            "method": "generate_stream",
            "messages_count": len(messages),
            "has_tools": tools is not None,
        })
        resp = self._next_response()
        if resp.tool_calls:
            yield StreamChunk(
                content_delta="",
                tool_calls_deltas=resp.tool_calls,
                finish_reason="tool_calls",
            )
        else:
            text = resp.content or ""
            for i in range(0, len(text), 10):
                chunk = text[i : i + 10]
                yield StreamChunk(content_delta=chunk, finish_reason=None)
            yield StreamChunk(content_delta="", finish_reason="stop")

    async def health_check(self) -> bool:
        """Simulate health check."""
        return self._healthy

    def get_model_info(self) -> Dict[str, Any]:
        """Return mock model info."""
        return {
            "provider": "mock",
            "model": "mock-model",
            "responses_queued": len(self._responses) - self._call_index,
            "calls_made": len(self._all_calls),
        }
