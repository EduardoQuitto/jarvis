"""Context Budget — explicit token budget management for LLM context.

Separates the context into named sections (system prompt, task context,
memory, history, tool definitions, current message, response reserve) so
the orchestrator can reason about tokens instead of message counts.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.contracts.llm import LLMMessage, LLMToolDef
from core.logger import get_logger

logger = get_logger("jarvis.context.budget")

DEFAULT_TOTAL_TOKENS = 8192
DEFAULT_RESPONSE_RESERVE = 1024
SAFETY_MARGIN = 0.85
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count (heuristic: ~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_tools_tokens(tools: Optional[List[LLMToolDef]]) -> int:
    """Estimate token count for a list of tool definitions."""
    if not tools:
        return 0
    total = 0
    for tool in tools:
        name = tool.function.name
        desc = tool.function.description
        params = str(tool.function.parameters)
        total += estimate_tokens(name) + estimate_tokens(desc) + estimate_tokens(params)
    return total


def estimate_message_tokens(message: LLMMessage) -> int:
    """Estimate token count for a single LLM message.

    Single centralized estimator (Phase 15.2 fix): accounts for the text
    content AND the tool-call structure (assistant tool_calls with names
    and serialized arguments, tool results with call ids/names). Every
    budget decision in ContextWindowManager/ConversationCompaction must
    use this function — never a content-only approximation.
    """
    total = estimate_tokens(message.content or "")
    if message.tool_calls:
        for tc in message.tool_calls:
            total += estimate_tokens(tc.id or "")
            total += estimate_tokens(tc.function.name or "")
            try:
                args_str = json.dumps(tc.function.arguments or {}, default=str)
            except Exception:
                args_str = str(tc.function.arguments)
            total += estimate_tokens(args_str)
    if message.tool_call_id:
        total += estimate_tokens(message.tool_call_id)
    if message.name:
        total += estimate_tokens(message.name)
    return total


def estimate_messages_tokens(messages: Optional[List[LLMMessage]]) -> int:
    """Estimate token count for a list of LLM messages (centralized)."""
    if not messages:
        return 0
    return sum(estimate_message_tokens(m) for m in messages)


@dataclass
class BudgetSection:
    """One named section of the context budget."""
    name: str
    allocated: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.allocated - self.used)

    @property
    def utilization(self) -> float:
        if self.allocated <= 0:
            return 1.0
        return self.used / self.allocated


@dataclass
class ProviderContextProfile:
    """Provider/model-specific context capabilities.

    The budget is derived from the provider's total token limit (prompt +
    completion), not from an arbitrary hardcoded value.
    """
    provider: str
    model: str
    total_token_limit: int
    max_output_tokens: int
    safety_margin: float = SAFETY_MARGIN

    @property
    def effective_budget(self) -> int:
        """Tokens available for prompt context (total * safety margin)."""
        return int(self.total_token_limit * self.safety_margin)

    @property
    def response_reserve(self) -> int:
        """Tokens reserved for the model's response."""
        return min(self.max_output_tokens, int(self.total_token_limit * 0.25))


KNOWN_PROFILES: Dict[str, ProviderContextProfile] = {
    "qwen3.5:4b": ProviderContextProfile("ollama", "qwen3.5:4b", 4096, 4096),
    "qwen2.5:7b": ProviderContextProfile("ollama", "qwen2.5:7b", 32768, 32768),
    "qwen2.5:14b": ProviderContextProfile("ollama", "qwen2.5:14b", 32768, 32768),
    "gemma2:9b": ProviderContextProfile("ollama", "gemma2:9b", 8192, 8192),
    "gemini-3.7-flash": ProviderContextProfile("google", "gemini-3.7-flash", 1048576, 65536),
    "gemini-2.5-flash": ProviderContextProfile("google", "gemini-2.5-flash", 1048576, 65536),
}


def get_provider_profile(provider: str = "ollama", model: str = "") -> ProviderContextProfile:
    """Get a context profile for the given provider/model.

    Falls back to a conservative default when the model is unknown.
    """
    key = model.lower() if model else provider.lower()
    for profile_key, profile in KNOWN_PROFILES.items():
        if profile_key in key:
            return profile
    return ProviderContextProfile(provider, model or "unknown", DEFAULT_TOTAL_TOKENS, DEFAULT_TOTAL_TOKENS // 4)


class ContextBudget:
    """Explicit token budget for one LLM call.

    Tracks how many tokens each section consumes and ensures the total
    stays within the provider's effective budget.
    """

    def __init__(
        self,
        total_tokens: int = DEFAULT_TOTAL_TOKENS,
        response_reserve: int = DEFAULT_RESPONSE_RESERVE,
    ):
        self.total_tokens = total_tokens
        self.response_reserve = response_reserve
        self.available_tokens = total_tokens - response_reserve
        self.sections: Dict[str, BudgetSection] = {}

    @classmethod
    def from_profile(cls, profile: ProviderContextProfile) -> "ContextBudget":
        """Create a budget from a provider profile."""
        return cls(
            total_tokens=profile.effective_budget,
            response_reserve=profile.response_reserve,
        )

    def allocate(self, name: str, tokens: int) -> bool:
        """Allocate tokens to a section. Returns False if over budget."""
        current_used = sum(s.used for s in self.sections.values())
        if current_used + tokens > self.available_tokens:
            logger.warning(
                "Budget overflow: section '%s' wants %d tokens, only %d available",
                name, tokens, self.available_tokens - current_used,
            )
            return False
        self.sections[name] = BudgetSection(name=name, allocated=tokens, used=tokens)
        return True

    def register_usage(self, name: str, tokens: int) -> None:
        """Register actual token usage for a section."""
        if name not in self.sections:
            self.sections[name] = BudgetSection(name=name, allocated=0, used=0)
        self.sections[name].used = tokens

    @property
    def used_tokens(self) -> int:
        return sum(s.used for s in self.sections.values())

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.available_tokens - self.used_tokens)

    @property
    def utilization(self) -> float:
        if self.available_tokens <= 0:
            return 1.0
        return self.used_tokens / self.available_tokens

    @property
    def is_over_budget(self) -> bool:
        return self.used_tokens > self.available_tokens

    def can_fit(self, tokens: int) -> bool:
        """Check if `tokens` more can fit in the remaining budget."""
        return self.used_tokens + tokens <= self.available_tokens

    def summary(self) -> Dict[str, any]:
        """Return a dict summary for observability."""
        return {
            "total_tokens": self.total_tokens,
            "available_tokens": self.available_tokens,
            "response_reserve": self.response_reserve,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "utilization": round(self.utilization, 3),
            "sections": {
                name: {
                    "allocated": s.allocated,
                    "used": s.used,
                    "remaining": s.remaining,
                    "utilization": round(s.utilization, 3),
                }
                for name, s in self.sections.items()
            },
        }
