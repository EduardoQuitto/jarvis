"""Context Builder — assembles full context for the LLM from multiple sources.

Integrates the Phase 15.2 context architecture: budget awareness, task
context, memory context, and compaction. The builder delegates to the
ContextWindowManager for budget-aware assembly.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.contracts.llm import LLMMessage, LLMToolDef
from core.contracts.enums import ToolVisibility
from core.llm.converters import tools_metadata_to_llm_defs
from core.context.budget import ContextBudget, ProviderContextProfile, get_provider_profile
from core.context.manager import ContextWindowManager
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("jarvis.context")


class ContextBuilder:
    """Assembles the full LLM context from system prompt, conversation, memory, and task state.

    Phase 15.2: Now budget-aware. Uses ContextWindowManager to assemble
    context within the provider's token budget, with compaction support.
    """

    def __init__(
        self,
        budget: Optional[ContextBudget] = None,
        window_manager: Optional[ContextWindowManager] = None,
    ):
        self._budget = budget
        self._window_manager = window_manager
        self._last_summary: Optional[dict] = None

    def _get_budget(self) -> ContextBudget:
        if self._budget is None:
            settings = get_settings()
            profile = get_provider_profile(
                provider=settings.llm_provider,
                model=settings.llm_model,
            )
            self._budget = ContextBudget.from_profile(profile)
        return self._budget

    def _get_window_manager(self) -> ContextWindowManager:
        if self._window_manager is None:
            self._window_manager = ContextWindowManager(budget=self._get_budget())
        return self._window_manager

    @property
    def max_output_tokens(self) -> Optional[int]:
        """Tokens to reserve for the LLM response (derived from provider profile).

        Returns None when the budget is disabled (legacy behavior: the
        provider decides). Never hardcoded per model here — the value
        comes from ProviderContextProfile via ContextBudget.
        """
        if not get_settings().context_budget_enabled:
            return None
        return self._get_budget().response_reserve

    @property
    def last_build_summary(self) -> Optional[dict]:
        """Budget summary of the most recent build (observability/tests)."""
        return self._last_summary

    @property
    def last_compaction(self):
        """Compaction result of the most recent build, if any."""
        if self._window_manager is None:
            return None
        return self._window_manager.get_compaction_result()

    def build(
        self,
        system_prompt: str,
        conversation_messages: Optional[List[LLMMessage]] = None,
        memory_context: Optional[str] = None,
        task_state: Optional[str] = None,
        current_time: Optional[str] = None,
        tools: Optional[List[LLMToolDef]] = None,
    ) -> List[LLMMessage]:
        """Build the complete message array for the LLM.

        Order: system → memory context → task state → conversation history

        Phase 15.2: Uses ContextWindowManager for budget-aware assembly
        with compaction support. This is the SINGLE rebuild path: the
        orchestrator calls it before EVERY LLM call (first turn and
        post-tool-call iterations alike), passing the in-memory messages
        (without the leading system message) plus the current tool defs
        so tool definitions enter the budget calculation.
        """
        settings = get_settings()

        if not settings.context_budget_enabled:
            return self._build_legacy(
                system_prompt, conversation_messages, memory_context, task_state, current_time,
            )

        wm = self._get_window_manager()
        result = wm.build_context(
            messages=conversation_messages or [],
            system_prompt=system_prompt,
            task_context=task_state,
            memory_context=memory_context,
            tools=tools,
        )
        self._last_summary = wm.budget.summary()
        return result

    def _build_legacy(
        self,
        system_prompt: str,
        conversation_messages: Optional[List[LLMMessage]],
        memory_context: Optional[str],
        task_state: Optional[str],
        current_time: Optional[str],
    ) -> List[LLMMessage]:
        """Legacy build path (budget disabled) — preserves original behavior."""
        messages: List[LLMMessage] = []

        full_system = system_prompt

        if memory_context:
            full_system += f"\n\n## Relevant Memory\n{memory_context}"

        if task_state:
            full_system += f"\n\n## Current Task State\n{task_state}"

        if not current_time:
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        full_system += f"\n\n## Current Time\n{current_time}"

        messages.append(LLMMessage(role="system", content=full_system))

        if conversation_messages:
            messages.extend(conversation_messages)

        return messages

    def build_tools_list(self, tool_metadata_list, shared_only: bool = False) -> List[LLMToolDef]:
        """Convert registry tool metadata to LLM tool definitions.

        Args:
            shared_only: If True, only include tools with visibility=SHARED.
                        Used when the next provider is external/untrusted.
        """
        if shared_only:
            tool_metadata_list = [
                t for t in tool_metadata_list
                if t.visibility == ToolVisibility.SHARED
            ]
        return tools_metadata_to_llm_defs(tool_metadata_list)
