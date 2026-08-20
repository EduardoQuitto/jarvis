"""LLM Provider package."""

from core.contracts.llm import BaseLLMProvider
from core.llm.provider import OllamaProvider
from core.llm.external_provider import ExternalProvider
from core.llm.mock_provider import MockLLMProvider
from core.llm.factory import create_llm_provider, create_router
from core.llm.registry import ProviderRegistry, get_provider_registry
from core.llm.router import IntelligenceRouter
from core.llm.converters import (
    tool_metadata_to_llm_def,
    parse_tool_calls,
    tool_result_to_message,
)

__all__ = [
    "BaseLLMProvider",
    "OllamaProvider",
    "ExternalProvider",
    "MockLLMProvider",
    "create_llm_provider",
    "create_router",
    "ProviderRegistry",
    "get_provider_registry",
    "IntelligenceRouter",
    "tool_metadata_to_llm_def",
    "parse_tool_calls",
    "tool_result_to_message",
]
