"""Tool Context Selection — deterministic tool selection for LLM calls.

Reduces the set of tools exposed to the model based on the current
context (user query, task state). This is NOT an authorization layer —
PolicyEngine, ToolVisibility, and ConfirmationManager remain the sole
authority for execution. This selector only decides which tools are
presented to the LLM in a given call.

Strategy:
- Keyword matching against tool name, description, and parameters.
- Always include core utility tools (echo, time, etc.).
- Fallback: if confidence is low, expand the set to avoid blocking.
- Respect visibility (SHARED for external providers).
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from core.contracts.tool import ToolMetadata
from core.contracts.enums import ToolVisibility
from core.context.budget import estimate_tokens, estimate_tools_tokens
from core.contracts.llm import LLMToolDef
from core.logger import get_logger

logger = get_logger("jarvis.context.tool_selector")

DEFAULT_MIN_TOOLS = 3
DEFAULT_CONFIDENCE_THRESHOLD = 0.3
DEFAULT_MAX_TOOLS = 15

CORE_TOOL_NAMES: Set[str] = {
    "echo",
    "get_time",
    "get_system_info",
    "search_memory",
    "search_file",
    "read_file",
}

KEYWORD_CATEGORIES: Dict[str, List[str]] = {
    "file": ["file", "read", "write", "directory", "folder", "path", "search", "list"],
    "system": ["system", "cpu", "memory", "disk", "process", "battery", "network", "status"],
    "app": ["app", "application", "open", "close", "launch", "program", "window"],
    "web": ["web", "search", "fetch", "url", "internet", "download", "http"],
    "task": ["task", "goal", "plan", "step", "progress", "status"],
    "notification": ["notify", "notification", "alert", "message", "send"],
    "device": ["device", "screen", "screenshot", "camera", "display"],
    "time": ["time", "date", "clock", "schedule", "timer"],
    "memory": ["memory", "remember", "recall", "search", "stored"],
    "ha": ["home", "assistant", "light", "switch", "sensor", "automation", "scene"],
}


@dataclass
class ToolSelectionResult:
    """Result of tool selection."""
    selected_tools: List[ToolMetadata]
    confidence: float
    fallback_used: bool
    selection_reason: str


class ToolContextSelector:
    """Deterministic tool selection based on metadata and context.

    Scores each tool by keyword relevance to the current query, always
    includes core tools, and falls back to a broader set when confidence
    is low.
    """

    def __init__(
        self,
        min_tools: int = DEFAULT_MIN_TOOLS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_tools: int = DEFAULT_MAX_TOOLS,
    ):
        self.min_tools = min_tools
        self.confidence_threshold = confidence_threshold
        self.max_tools = max_tools

    def select(
        self,
        tools: List[ToolMetadata],
        query: str = "",
        shared_only: bool = False,
    ) -> ToolSelectionResult:
        """Select tools relevant to the current query.

        Args:
            tools: All available tools from the registry.
            query: The user's current message.
            shared_only: If True, only SHARED visibility tools (external provider).

        Returns:
            ToolSelectionResult with selected tools and confidence.
        """
        if not tools:
            return ToolSelectionResult([], 0.0, False, "no_tools_available")

        # Filter by visibility first
        if shared_only:
            tools = [t for t in tools if t.visibility == ToolVisibility.SHARED]

        if not tools:
            return ToolSelectionResult([], 0.0, False, "no_shared_tools")

        # Score each tool
        query_lower = query.lower()
        query_tokens = self._tokenize(query_lower)

        scored: List[tuple] = []
        for tool in tools:
            score = self._score_tool(tool, query_lower, query_tokens)
            scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Always include core tools
        core_tools = [t for t in tools if t.name in CORE_TOOL_NAMES]
        core_names = {t.name for t in core_tools}

        # Select top-scored tools
        selected: List[ToolMetadata] = []
        selected_names: Set[str] = set()

        for score, tool in scored:
            if len(selected) >= self.max_tools:
                break
            if tool.name not in selected_names:
                selected.append(tool)
                selected_names.add(tool.name)

        # Ensure core tools are included
        for tool in core_tools:
            if tool.name not in selected_names and len(selected) < self.max_tools:
                selected.append(tool)
                selected_names.add(tool.name)

        # Calculate confidence
        confidence = self._calculate_confidence(scored, query_tokens)

        # Fallback: if confidence is low, expand the set beyond max_tools
        fallback_used = False
        if confidence < self.confidence_threshold and len(selected) < len(tools):
            fallback_used = True
            fallback_limit = min(len(tools), self.max_tools * 2)
            for tool in tools:
                if tool.name not in selected_names and len(selected) < fallback_limit:
                    selected.append(tool)
                    selected_names.add(tool.name)
            logger.info(
                "Tool selection fallback: expanded to %d tools (confidence %.2f)",
                len(selected), confidence,
            )

        return ToolSelectionResult(
            selected_tools=selected,
            confidence=confidence,
            fallback_used=fallback_used,
            selection_reason=f"selected_{len(selected)}_of_{len(tools)}_tools",
        )

    def _tokenize(self, text: str) -> Set[str]:
        """Extract meaningful tokens from text."""
        words = re.findall(r"[a-z_]{3,}", text)
        return set(words)

    def _score_tool(self, tool: ToolMetadata, query_lower: str, query_tokens: Set[str]) -> float:
        """Score a tool's relevance to the query."""
        score = 0.0
        name = tool.name.lower()
        desc = tool.description.lower()

        # Name match (highest weight)
        if name in query_lower:
            score += 3.0
        for token in query_tokens:
            if token in name:
                score += 1.5

        # Description match
        for token in query_tokens:
            if token in desc:
                score += 0.5

        # Category match
        for category, keywords in KEYWORD_CATEGORIES.items():
            if any(kw in name or kw in desc for kw in keywords):
                if any(kw in query_lower for kw in keywords):
                    score += 1.0

        # Parameter match
        params = str(tool.parameters_schema).lower()
        for token in query_tokens:
            if token in params:
                score += 0.3

        # Core tools get a baseline score
        if tool.name in CORE_TOOL_NAMES:
            score += 0.5

        return score

    def _calculate_confidence(self, scored: List[tuple], query_tokens: Set[str]) -> float:
        """Calculate confidence in the selection.

        High confidence: strong keyword matches found.
        Low confidence: few or no matches.
        """
        if not query_tokens:
            return 0.5

        max_score = scored[0][0] if scored else 0
        if max_score >= 3.0:
            return 1.0
        if max_score >= 1.5:
            return 0.7
        if max_score >= 0.5:
            return 0.4
        return 0.2
