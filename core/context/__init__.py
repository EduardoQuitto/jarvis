"""Context architecture package — budget, compaction, task context, tool selection."""

from core.context.budget import (
    ContextBudget,
    ProviderContextProfile,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    estimate_tools_tokens,
    get_provider_profile,
)
from core.context.compaction import ConversationCompaction, CompactionResult
from core.context.task_context import TaskContextBuilder
from core.context.tool_selector import ToolContextSelector, ToolSelectionResult
from core.context.manager import ContextWindowManager

__all__ = [
    "ContextBudget",
    "ProviderContextProfile",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_tokens",
    "estimate_tools_tokens",
    "get_provider_profile",
    "ConversationCompaction",
    "CompactionResult",
    "TaskContextBuilder",
    "ToolContextSelector",
    "ToolSelectionResult",
    "ContextWindowManager",
]
