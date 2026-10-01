"""Conversation Compaction — deterministic compaction for long conversations.

Strategy:
- Detect when context grows beyond a threshold (token-based).
- Compact older messages into a structured summary.
- Preserve the most recent messages verbatim.
- NEVER delete the original history — compaction produces a representation.
- The summary is deterministic (structure extraction, not LLM-generated).
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.contracts.llm import LLMMessage
from core.context.budget import estimate_messages_tokens, estimate_tokens
from core.logger import get_logger

logger = get_logger("jarvis.context.compaction")

DEFAULT_COMPACT_THRESHOLD = 0.7
DEFAULT_KEEP_RECENT = 10
DEFAULT_KEEP_RECENT_TOKENS = 2048


@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    summary: str
    compacted_count: int
    preserved_count: int
    total_tokens_before: int
    total_tokens_after: int


class ConversationCompaction:
    """Deterministic conversation compaction.

    When the conversation grows beyond the threshold, older messages are
    summarized into a compact structured form. The recent messages are
    kept verbatim. The original messages are never deleted.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_COMPACT_THRESHOLD,
        keep_recent: int = DEFAULT_KEEP_RECENT,
        keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
    ):
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.keep_recent_tokens = keep_recent_tokens

    def should_compact(
        self,
        messages: List[LLMMessage],
        budget_tokens: int,
    ) -> bool:
        """Check if the conversation should be compacted.

        Compaction triggers when the estimated token count exceeds
        the threshold percentage of the available budget.
        """
        total_tokens = estimate_messages_tokens(messages)
        return total_tokens > int(budget_tokens * self.threshold)

    def compact(self, messages: List[LLMMessage]) -> CompactionResult:
        """Compact messages into a summary + recent messages.

        The summary is a deterministic extraction of:
        - User requests
        - Assistant text responses
        - Tool calls and their outcomes
        - Key decisions and results

        The original messages are NOT modified or deleted.
        """
        if len(messages) <= self.keep_recent:
            total_tokens = estimate_messages_tokens(messages)
            return CompactionResult(
                summary="",
                compacted_count=0,
                preserved_count=len(messages),
                total_tokens_before=total_tokens,
                total_tokens_after=total_tokens,
            )

        # Split: older messages to summarize, recent to keep
        split_point = len(messages) - self.keep_recent
        older = messages[:split_point]
        recent = messages[split_point:]

        summary = self._build_summary(older)
        total_before = estimate_messages_tokens(messages)
        total_after = estimate_tokens(summary) + estimate_messages_tokens(recent)

        logger.info(
            "Compacted %d messages into summary (%d tokens -> %d tokens)",
            len(older), total_before, total_after,
        )

        return CompactionResult(
            summary=summary,
            compacted_count=len(older),
            preserved_count=len(recent),
            total_tokens_before=total_before,
            total_tokens_after=total_after,
        )

    def _build_summary(self, messages: List[LLMMessage]) -> str:
        """Build a deterministic summary from older messages.

        Extracts:
        - User requests (role=user)
        - Assistant responses (role=assistant, no tool calls)
        - Tool call outcomes (role=tool: success/failure)
        """
        user_requests: List[str] = []
        assistant_responses: List[str] = []
        tool_outcomes: List[str] = []

        for msg in messages:
            content = (msg.content or "").strip()
            if not content and not msg.tool_calls:
                continue

            if msg.role == "user":
                user_requests.append(content[:200])
            elif msg.role == "assistant":
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        tool_outcomes.append(f"Called: {tool_name}")
                if content:
                    assistant_responses.append(content[:200])
            elif msg.role == "tool":
                name = msg.name or "unknown"
                success = not content.startswith("Error:")
                status = "OK" if success else "FAILED"
                tool_outcomes.append(f"{name}: {status}")

        parts: List[str] = []
        if user_requests:
            parts.append("Previous requests:\n" + "\n".join(f"- {r}" for r in user_requests[-10:]))
        if assistant_responses:
            parts.append("Previous responses:\n" + "\n".join(f"- {r}" for r in assistant_responses[-10:]))
        if tool_outcomes:
            parts.append("Tool activity:\n" + "\n".join(f"- {t}" for t in tool_outcomes[-15:]))

        return "\n\n".join(parts) if parts else "(no summary available)"

    def merge_summary_with_recent(
        self,
        summary: str,
        recent_messages: List[LLMMessage],
    ) -> List[LLMMessage]:
        """Merge a compaction summary with recent messages.

        The summary becomes a system message prepended to the recent messages.
        This preserves the tool call sequence validity.
        """
        if not summary:
            return recent_messages

        result = [LLMMessage(role="system", content=f"[Conversation Summary]\n{summary}")]
        result.extend(recent_messages)
        return result
