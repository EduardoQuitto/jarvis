"""Contracts for LLM Provider abstraction and structured tool calling."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel, Field


class LLMFunctionCall(BaseModel):
    """Parsed function call inside a tool call."""
    name: str = Field(..., description="Function/tool name to invoke")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Parsed JSON arguments")


class LLMToolCall(BaseModel):
    """A single tool call returned by the LLM."""
    id: str = Field(..., description="Unique tool call identifier")
    type: str = Field(default="function", description="Tool call type")
    function: LLMFunctionCall = Field(..., description="Function call details")


class LLMMessage(BaseModel):
    """A message in the LLM conversation format."""
    role: str = Field(..., description="Message role: system, user, assistant, tool")
    content: str = Field(default="", description="Text content of the message")
    tool_calls: Optional[List[LLMToolCall]] = Field(default=None, description="Tool calls (assistant role)")
    tool_call_id: Optional[str] = Field(default=None, description="Tool call ID this result responds to (tool role)")
    name: Optional[str] = Field(default=None, description="Tool name (tool role)")


class LLMFunctionSchema(BaseModel):
    """Schema for a single function/tool definition."""
    name: str = Field(..., description="Unique function name")
    description: str = Field(..., description="Human-readable description")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for parameters")


class LLMToolDef(BaseModel):
    """Tool definition in the format expected by OpenAI-compatible APIs."""
    type: str = Field(default="function", description="Tool type")
    function: LLMFunctionSchema = Field(..., description="Function schema")


class LLMUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)


class LLMResponse(BaseModel):
    """Structured response from the LLM."""
    content: Optional[str] = Field(default=None, description="Text content if any")
    tool_calls: List[LLMToolCall] = Field(default_factory=list, description="Tool calls requested")
    finish_reason: str = Field(default="stop", description="stop, tool_calls, or length")
    usage: Optional[LLMUsage] = Field(default=None, description="Token usage")
    model: str = Field(default="", description="Model that generated the response")
    error_msg: Optional[str] = Field(default=None, description="Error message if the provider failed")


class StreamChunk(BaseModel):
    """A single chunk from a streaming response."""
    content_delta: str = Field(default="", description="Text delta to append")
    tool_calls_deltas: List[LLMToolCall] = Field(default_factory=list, description="Tool call deltas")
    finish_reason: Optional[str] = Field(default=None, description="Finish reason if last chunk")


class BaseLLMProvider(ABC):
    """Abstract interface that all LLM providers must implement."""

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a complete response from the LLM."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Generate a streaming response from the LLM."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM provider is reachable and healthy."""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return information about the configured model."""
        pass
