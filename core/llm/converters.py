"""Converters between JARVIS ToolRegistry format and LLM tool-calling format."""

import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.contracts.llm import LLMMessage, LLMToolCall, LLMToolDef, LLMFunctionCall, LLMFunctionSchema
from core.contracts.tool import ToolMetadata
from core.contracts.tool import ToolResult


def tool_metadata_to_llm_def(tool: ToolMetadata) -> LLMToolDef:
    """Convert a ToolMetadata from the registry into an LLM tool definition.

    This bridges the existing ToolRegistry with LLM tool-calling format.
    """
    return LLMToolDef(
        type="function",
        function=LLMFunctionSchema(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters_schema or {
                "type": "object",
                "properties": {},
            },
        ),
    )


def tools_metadata_to_llm_defs(tools: List[ToolMetadata]) -> List[LLMToolDef]:
    """Convert a list of ToolMetadata into LLM tool definitions."""
    return [tool_metadata_to_llm_def(t) for t in tools]


def parse_tool_calls(llm_tool_calls: List[LLMToolCall]) -> List[Tuple[str, Dict[str, Any], str]]:
    """Parse LLM tool calls into a list of (tool_name, arguments, call_id) tuples.

    Returns:
        List of (tool_name, arguments_dict, call_id) tuples ready for execution.
    """
    result = []
    for tc in llm_tool_calls:
        result.append((tc.function.name, tc.function.arguments, tc.id))
    return result


def tool_result_to_message(
    tool_name: str,
    call_id: str,
    result: ToolResult,
) -> LLMMessage:
    """Convert a ToolResult into an LLM message with role='tool'.

    This creates the message that gets appended to conversation history
    after a tool has been executed, so the LLM can see the result.
    """
    if result.success:
        content = str(result.data) if result.data is not None else "Tool executed successfully."
    else:
        content = f"Error: {result.error}" if result.error else "Tool execution failed."

    return LLMMessage(
        role="tool",
        content=content,
        tool_call_id=call_id,
        name=tool_name,
    )


def create_tool_call_id() -> str:
    """Generate a unique ID for a tool call."""
    return f"call-{uuid.uuid4().hex[:8]}"
