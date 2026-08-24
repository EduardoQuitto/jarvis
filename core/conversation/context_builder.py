"""Context Builder — assembles full context for the LLM from multiple sources."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.contracts.llm import LLMMessage, LLMToolDef
from core.contracts.enums import ToolVisibility
from core.llm.converters import tools_metadata_to_llm_defs
from core.logger import get_logger

logger = get_logger("jarvis.context")


class ContextBuilder:
    """Assembles the full LLM context from system prompt, conversation, memory, tools, and task state."""

    def build(
        self,
        system_prompt: str,
        conversation_messages: Optional[List[LLMMessage]] = None,
        memory_context: Optional[str] = None,
        task_state: Optional[str] = None,
        current_time: Optional[str] = None,
    ) -> List[LLMMessage]:
        """Build the complete message array for the LLM.

        Order: system → memory context → task state → conversation history
        """
        messages: List[LLMMessage] = []

        # System prompt — always first
        full_system = system_prompt

        # Inject memory context if available
        if memory_context:
            full_system += f"\n\n## Relevant Memory\n{memory_context}"

        # Inject task state if available
        if task_state:
            full_system += f"\n\n## Current Task State\n{task_state}"

        # Inject current time
        if not current_time:
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        full_system += f"\n\n## Current Time\n{current_time}"

        messages.append(LLMMessage(role="system", content=full_system))

        # Add conversation history
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
