"""Context Window Manager — prioritized, budget-aware context assembly.

Evolves the simple "last N messages" window into a prioritized,
budget-aware context manager that:
- Applies compaction when the conversation grows too large.
- Accounts for tool definitions in the budget.
- Enforces the budget by trimming old history (never the active turn).
- Preserves tool call sequences (never starts mid-sequence).
- Integrates task context and memory.
"""

from typing import List, Optional

from core.contracts.llm import LLMMessage, LLMToolDef
from core.context.budget import (
    ContextBudget,
    estimate_messages_tokens,
    estimate_tokens,
    estimate_tools_tokens,
)
from core.context.compaction import ConversationCompaction, CompactionResult
from core.logger import get_logger

logger = get_logger("jarvis.context.manager")


class ContextWindowManager:
    """Manages the context window with prioritization and budget awareness.

    Single enforcement point for the prompt budget (Phase 15.2 fix):
    1. Estimates system + task + memory + tool definitions + history with
       the centralized estimators from core.context.budget.
    2. Compacts old messages when the threshold is exceeded.
    3. Trims old history (pair-aware) until the prompt fits the budget,
       never touching the active turn (last user message onward).
    4. Never starts the context with an orphan tool message.
    5. Tracks token usage against the budget.
    """

    def __init__(
        self,
        budget: Optional[ContextBudget] = None,
        compaction: Optional[ConversationCompaction] = None,
    ):
        self.budget = budget or ContextBudget()
        self.compaction = compaction or ConversationCompaction()
        self._last_compaction: Optional[CompactionResult] = None

    def build_context(
        self,
        messages: List[LLMMessage],
        system_prompt: str = "",
        task_context: Optional[str] = None,
        memory_context: Optional[str] = None,
        tools: Optional[List[LLMToolDef]] = None,
    ) -> List[LLMMessage]:
        """Build the final context for the LLM, guaranteed within budget.

        Steps:
        1. Estimate every section (system/task/memory/tools/history).
        2. Compact if over threshold.
        3. Trim old history (pair-aware) until the prompt fits.
        4. Prepend system prompt + task context + memory.
        5. Ensure tool call sequence validity.
        """
        self._last_compaction = None

        system_tokens = estimate_tokens(system_prompt)
        task_tokens = estimate_tokens(task_context) if task_context else 0
        memory_tokens = estimate_tokens(memory_context) if memory_context else 0
        tools_tokens = estimate_tools_tokens(tools)

        fixed_tokens = system_tokens + task_tokens + memory_tokens + tools_tokens
        room_for_history = max(0, self.budget.available_tokens - fixed_tokens)

        # Step 2: compact if needed, then strip leading orphan tools whose
        # assistant call was compacted away.
        summary = ""
        final_messages = list(messages)
        compacted = False
        if self.compaction.should_compact(final_messages, room_for_history):
            result = self.compaction.compact(final_messages)
            if result.compacted_count > 0:
                split = len(final_messages) - result.preserved_count
                recent = final_messages[split:]
                while recent and recent[0].role == "tool":
                    dropped = recent.pop(0)
                    logger.debug(
                        "Dropping orphan tool message after compaction split (call_id=%s)",
                        dropped.tool_call_id,
                    )
                summary = result.summary
                final_messages = recent
                compacted = True
                self._last_compaction = result

        # Step 3: enforce the budget — trim old history until it fits.
        final_messages = self._trim_to_fit(final_messages, room_for_history)

        # Step 4: build the full context
        result_messages: List[LLMMessage] = []
        full_system = system_prompt
        if task_context:
            full_system += f"\n\n## Current Task State\n{task_context}"
        if memory_context:
            full_system += f"\n\n## Relevant Memory\n{memory_context}"
        result_messages.append(LLMMessage(role="system", content=full_system))
        if summary:
            result_messages.append(
                LLMMessage(role="system", content=f"[Conversation Summary]\n{summary}")
            )
        result_messages.extend(final_messages)

        # Step 5: never start with an orphan tool message
        while len(result_messages) > 1 and result_messages[1].role == "tool":
            result_messages.pop(1)

        # Step 6: track budget usage
        self.budget.register_usage("system_prompt", system_tokens)
        if task_context:
            self.budget.register_usage("task_context", task_tokens)
        if memory_context:
            self.budget.register_usage("memory", memory_tokens)
        self.budget.register_usage("tool_definitions", tools_tokens)
        self.budget.register_usage("history", estimate_messages_tokens(final_messages))

        logger.info(
            "Context built: %d messages, %d/%d prompt tokens (tools=%d, compacted=%s)",
            len(result_messages), self.budget.used_tokens,
            self.budget.available_tokens, len(tools or []), compacted,
        )
        if self.budget.is_over_budget:
            logger.warning(
                "Context still over budget after trim (%d > %d); "
                "active turn preserved, provider may truncate",
                self.budget.used_tokens, self.budget.available_tokens,
            )

        return result_messages

    def _trim_to_fit(
        self,
        messages: List[LLMMessage],
        room_tokens: int,
    ) -> List[LLMMessage]:
        """Trim old history until it fits `room_tokens`.

        Pair-aware: an assistant message carrying tool_calls is dropped
        together with its following tool results, so a kept assistant call
        never loses its results. The active turn (last user message onward,
        which includes the current user request) is never trimmed.
        """
        msgs = list(messages)
        while estimate_messages_tokens(msgs) > room_tokens and msgs:
            if self._active_turn_start(msgs) <= 0:
                break
            first = msgs[0]
            if first.role == "assistant" and first.tool_calls:
                msgs.pop(0)
                # Drop the tool results answering the dropped call, but
                # never cross into the protected active turn.
                while msgs and msgs[0].role == "tool" and self._active_turn_start(msgs) > 0:
                    msgs.pop(0)
            else:
                # user / assistant-text / orphan tool: drop one message.
                msgs.pop(0)
        return msgs

    @staticmethod
    def _active_turn_start(messages: List[LLMMessage]) -> int:
        """Index of the last user message; everything from there is protected."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "user":
                return i
        return 0

    def should_compact(self, messages: List[LLMMessage]) -> bool:
        """Check if the current messages should be compacted."""
        return self.compaction.should_compact(messages, self.budget.available_tokens)

    def get_compaction_result(self) -> Optional[CompactionResult]:
        """Get the last compaction result (for observability)."""
        return self._last_compaction
