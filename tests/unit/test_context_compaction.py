"""Tests for Conversation Compaction (Phase 15.2)."""

import pytest

from core.context.compaction import ConversationCompaction, CompactionResult
from core.context.budget import estimate_tokens
from core.contracts.llm import LLMMessage, LLMToolCall, LLMFunctionCall


def _make_messages(count: int, with_tool_calls: bool = False) -> list:
    messages = []
    for i in range(count):
        messages.append(LLMMessage(role="user", content=f"user message {i} " + "x" * 100))
        if with_tool_calls:
            tc = LLMToolCall(
                id=f"call-{i}",
                type="function",
                function=LLMFunctionCall(name="echo", arguments={"message": f"test {i}"}),
            )
            messages.append(LLMMessage(role="assistant", content="", tool_calls=[tc]))
            messages.append(LLMMessage(role="tool", content=f"result {i}", tool_call_id=f"call-{i}", name="echo"))
        else:
            messages.append(LLMMessage(role="assistant", content=f"assistant response {i} " + "y" * 100))
    return messages


class TestShouldCompact:
    def test_small_history_does_not_trigger(self):
        compaction = ConversationCompaction(threshold=0.7, keep_recent=5)
        messages = _make_messages(3)
        assert not compaction.should_compact(messages, 10000)

    def test_large_history_triggers(self):
        compaction = ConversationCompaction(threshold=0.7, keep_recent=5)
        messages = _make_messages(50)
        assert compaction.should_compact(messages, 1000)

    def test_empty_history_does_not_trigger(self):
        compaction = ConversationCompaction()
        assert not compaction.should_compact([], 1000)


class TestCompact:
    def test_small_history_not_compacted(self):
        compaction = ConversationCompaction(keep_recent=10)
        messages = _make_messages(5)
        result = compaction.compact(messages)
        assert result.compacted_count == 0
        assert result.summary == ""

    def test_large_history_compacted(self):
        compaction = ConversationCompaction(keep_recent=5)
        messages = _make_messages(30)
        result = compaction.compact(messages)
        assert result.compacted_count == len(messages) - 5
        assert result.preserved_count == 5
        assert result.summary != ""
        assert result.total_tokens_after < result.total_tokens_before

    def test_summary_contains_user_requests(self):
        compaction = ConversationCompaction(keep_recent=3)
        messages = _make_messages(20)
        result = compaction.compact(messages)
        assert "user message" in result.summary

    def test_summary_contains_tool_activity(self):
        compaction = ConversationCompaction(keep_recent=3)
        messages = _make_messages(20, with_tool_calls=True)
        result = compaction.compact(messages)
        assert "echo" in result.summary

    def test_original_messages_not_modified(self):
        compaction = ConversationCompaction(keep_recent=5)
        messages = _make_messages(30)
        original_contents = [m.content for m in messages]
        compaction.compact(messages)
        assert [m.content for m in messages] == original_contents


class TestMergeSummaryWithRecent:
    def test_merge_produces_valid_sequence(self):
        compaction = ConversationCompaction(keep_recent=5)
        messages = _make_messages(30, with_tool_calls=True)
        result = compaction.compact(messages)
        recent = messages[-result.preserved_count:]
        merged = compaction.merge_summary_with_recent(result.summary, recent)
        assert merged[0].role == "system"
        assert "Conversation Summary" in merged[0].content
        assert len(merged) == len(recent) + 1

    def test_merge_empty_summary_returns_recent(self):
        compaction = ConversationCompaction()
        recent = [LLMMessage(role="user", content="hello")]
        merged = compaction.merge_summary_with_recent("", recent)
        assert merged == recent

    def test_merged_sequence_no_orphan_tool(self):
        compaction = ConversationCompaction(keep_recent=5)
        messages = _make_messages(30, with_tool_calls=True)
        result = compaction.compact(messages)
        recent = messages[-result.preserved_count:]
        merged = compaction.merge_summary_with_recent(result.summary, recent)
        while merged and merged[0].role == "tool":
            merged.pop(0)
        assert merged[0].role != "tool"
