"""Integration tests for Phase 15.2 Context Architecture."""

import json
import pytest

from core.context.budget import ContextBudget, ProviderContextProfile, estimate_tokens
from core.context.compaction import ConversationCompaction
from core.context.manager import ContextWindowManager
from core.context.tool_selector import ToolContextSelector
from core.context.task_context import TaskContextBuilder
from core.conversation.manager import ConversationManager
from core.conversation.context_builder import ContextBuilder
from core.contracts.llm import LLMMessage, LLMToolCall, LLMFunctionCall, LLMToolDef, LLMFunctionSchema
from core.contracts.task import Task, TaskCheckpoint
from core.contracts.enums import TaskStatus, ToolVisibility, SecurityLevel
from core.contracts.tool import ToolMetadata


class TestContextWindowManager:
    def test_small_history_no_compaction(self):
        budget = ContextBudget(total_tokens=8192, response_reserve=1024)
        wm = ContextWindowManager(budget=budget)
        messages = [LLMMessage(role="user", content="hello"), LLMMessage(role="assistant", content="hi")]
        result = wm.build_context(messages, system_prompt="You are JARVIS")
        assert len(result) == 3
        assert result[0].role == "system"

    def test_large_history_triggers_compaction(self):
        budget = ContextBudget(total_tokens=2048, response_reserve=256)
        compaction = ConversationCompaction(threshold=0.5, keep_recent=3)
        wm = ContextWindowManager(budget=budget, compaction=compaction)
        messages = [LLMMessage(role="user", content="x" * 500) for _ in range(20)]
        result = wm.build_context(messages, system_prompt="You are JARVIS")
        assert result[0].role == "system"
        assert any("Conversation Summary" in m.content for m in result)

    def test_task_context_included(self):
        budget = ContextBudget(total_tokens=8192, response_reserve=1024)
        wm = ContextWindowManager(budget=budget)
        messages = [LLMMessage(role="user", content="hello")]
        result = wm.build_context(
            messages,
            system_prompt="You are JARVIS",
            task_context="TASK\nBuild app",
        )
        system_content = result[0].content
        assert "Build app" in system_content

    def test_memory_context_included(self):
        budget = ContextBudget(total_tokens=8192, response_reserve=1024)
        wm = ContextWindowManager(budget=budget)
        messages = [LLMMessage(role="user", content="hello")]
        result = wm.build_context(
            messages,
            system_prompt="You are JARVIS",
            memory_context="- key: value",
        )
        system_content = result[0].content
        assert "Relevant Memory" in system_content

    def test_no_orphan_tool_at_start(self):
        budget = ContextBudget(total_tokens=8192, response_reserve=1024)
        wm = ContextWindowManager(budget=budget)
        messages = [
            LLMMessage(role="tool", content="orphan result", tool_call_id="call-1", name="echo"),
            LLMMessage(role="assistant", content="done"),
        ]
        result = wm.build_context(messages, system_prompt="You are JARVIS")
        assert result[0].role != "tool"

    def test_budget_tracking(self):
        budget = ContextBudget(total_tokens=8192, response_reserve=1024)
        wm = ContextWindowManager(budget=budget)
        messages = [LLMMessage(role="user", content="hello " + "x" * 100)]
        wm.build_context(messages, system_prompt="You are JARVIS")
        assert budget.used_tokens > 0
        assert "system_prompt" in budget.sections
        assert "history" in budget.sections


class TestContextBuilderIntegration:
    def test_build_with_budget_enabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CONTEXT_BUDGET_ENABLED", "true")
        from core.config import reset_settings
        reset_settings()
        builder = ContextBuilder()
        messages = [LLMMessage(role="user", content="hello")]
        result = builder.build(
            system_prompt="You are JARVIS",
            conversation_messages=messages,
            task_state="TASK\nTest",
            memory_context="- fact: value",
        )
        assert result[0].role == "system"
        assert "Test" in result[0].content
        assert "Relevant Memory" in result[0].content

    def test_build_with_budget_disabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CONTEXT_BUDGET_ENABLED", "false")
        from core.config import reset_settings
        reset_settings()
        builder = ContextBuilder()
        messages = [LLMMessage(role="user", content="hello")]
        result = builder.build(
            system_prompt="You are JARVIS",
            conversation_messages=messages,
            task_state="TASK\nTest",
        )
        assert result[0].role == "system"
        assert "Test" in result[0].content


class TestCompactionPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_summary(self, tmp_path):
        from memory.sqlite_provider import SQLiteMemoryProvider
        db = str(tmp_path / "test.db")
        mem = SQLiteMemoryProvider(db_path=db)
        await mem.initialize()
        await mem.create_conversation("sess-1", title="test")
        summary_id = await mem.save_conversation_summary("sess-1", "Test summary", compacted_count=10)
        assert summary_id > 0
        summaries = await mem.get_conversation_summaries("sess-1")
        assert len(summaries) == 1
        assert summaries[0]["summary_text"] == "Test summary"
        assert summaries[0]["compacted_count"] == 10

    @pytest.mark.asyncio
    async def test_get_latest_summary(self, tmp_path):
        from memory.sqlite_provider import SQLiteMemoryProvider
        db = str(tmp_path / "test.db")
        mem = SQLiteMemoryProvider(db_path=db)
        await mem.initialize()
        await mem.create_conversation("sess-1", title="test")
        await mem.save_conversation_summary("sess-1", "First summary")
        await mem.save_conversation_summary("sess-1", "Second summary")
        latest = await mem.get_latest_conversation_summary("sess-1")
        assert latest["summary_text"] == "Second summary"

    @pytest.mark.asyncio
    async def test_conversation_manager_summary_methods(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
        from core.config import reset_settings
        reset_settings()
        manager = ConversationManager()
        session_id = await manager.create_session(title="test")
        await manager.save_compaction_summary(session_id, "Summary text", compacted_count=5)
        summaries = await manager.get_compaction_summaries(session_id)
        assert len(summaries) == 1
        assert summaries[0]["summary_text"] == "Summary text"


class TestToolSelectionIntegration:
    def test_28_tools_reduction(self):
        selector = ToolContextSelector(max_tools=10)
        tools = []
        for i in range(28):
            tools.append(ToolMetadata(
                name=f"tool_{i}",
                description=f"Tool number {i} for testing",
                security_level=SecurityLevel.GREEN,
                visibility=ToolVisibility.LOCAL_ONLY,
                parameters_schema={"type": "object", "properties": {}},
            ))
        result = selector.select(tools, query="tool")
        assert len(result.selected_tools) < 28
        assert len(result.selected_tools) <= 10

    def test_tool_selection_reduces_prompt_tokens(self):
        selector = ToolContextSelector(max_tools=5)
        tools = []
        for i in range(28):
            tools.append(ToolMetadata(
                name=f"tool_{i}",
                description=f"Tool number {i} with a long description " + "x" * 100,
                security_level=SecurityLevel.GREEN,
                visibility=ToolVisibility.LOCAL_ONLY,
                parameters_schema={"type": "object", "properties": {"param": {"type": "string"}}},
            ))
        all_tokens = sum(
            estimate_tokens(t.name) + estimate_tokens(t.description) + estimate_tokens(str(t.parameters_schema))
            for t in tools
        )
        result = selector.select(tools, query="tool")
        selected_tokens = sum(
            estimate_tokens(t.name) + estimate_tokens(t.description) + estimate_tokens(str(t.parameters_schema))
            for t in result.selected_tools
        )
        assert selected_tokens < all_tokens


class TestProviderAwareBudget:
    def test_qwen35_4b_budget(self):
        profile = ProviderContextProfile("ollama", "qwen3.5:4b", 4096, 4096)
        budget = ContextBudget.from_profile(profile)
        assert budget.total_tokens < 4096
        assert budget.response_reserve > 0

    def test_gemini_budget(self):
        profile = ProviderContextProfile("google", "gemini-3.7-flash", 1048576, 65536)
        budget = ContextBudget.from_profile(profile)
        assert budget.total_tokens > 100000

    def test_budget_differs_by_provider(self):
        qwen = ContextBudget.from_profile(ProviderContextProfile("ollama", "qwen3.5:4b", 4096, 4096))
        gemini = ContextBudget.from_profile(ProviderContextProfile("google", "gemini-3.7-flash", 1048576, 65536))
        assert qwen.total_tokens < gemini.total_tokens


class TestLongSessionSimulation:
    @pytest.mark.asyncio
    async def test_long_session_stays_controlled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
        from core.config import reset_settings
        reset_settings()

        manager = ConversationManager(max_context_messages=100)
        session_id = await manager.create_session(title="long session")

        for i in range(100):
            await manager.append_message(session_id, "user", f"message {i} " + "x" * 200)
            await manager.append_message(session_id, "assistant", f"response {i} " + "y" * 200)

        history = await manager.get_context_window(session_id)
        total_tokens = sum(estimate_tokens(m.content or "") for m in history)
        assert total_tokens < 50000

    @pytest.mark.asyncio
    async def test_restart_preserves_history(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
        from core.config import reset_settings
        reset_settings()

        manager = ConversationManager(max_context_messages=100)
        session_id = await manager.create_session(title="restart test")
        for i in range(20):
            await manager.append_message(session_id, "user", f"message {i}")

        manager2 = ConversationManager(max_context_messages=100)
        history = await manager2.get_context_window(session_id)
        assert len(history) == 20

    @pytest.mark.asyncio
    async def test_compaction_after_restart(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
        from core.config import reset_settings
        reset_settings()

        manager = ConversationManager(max_context_messages=100)
        session_id = await manager.create_session(title="compaction test")
        for i in range(50):
            await manager.append_message(session_id, "user", f"message {i} " + "x" * 300)

        await manager.save_compaction_summary(session_id, "Old messages summary", compacted_count=40)

        manager2 = ConversationManager(max_context_messages=100)
        summaries = await manager2.get_compaction_summaries(session_id)
        assert len(summaries) == 1
        assert summaries[0]["compacted_count"] == 40

        history = await manager2.get_context_window(session_id)
        assert len(history) > 0


class TestToolSequenceValidity:
    def test_tool_call_sequence_preserved_in_compaction(self):
        compaction = ConversationCompaction(keep_recent=5)
        messages = []
        for i in range(20):
            messages.append(LLMMessage(role="user", content=f"do {i}"))
            tc = LLMToolCall(
                id=f"call-{i}",
                type="function",
                function=LLMFunctionCall(name="echo", arguments={"message": str(i)}),
            )
            messages.append(LLMMessage(role="assistant", content="", tool_calls=[tc]))
            messages.append(LLMMessage(role="tool", content=f"result {i}", tool_call_id=f"call-{i}", name="echo"))

        result = compaction.compact(messages)
        recent = messages[-result.preserved_count:]
        merged = compaction.merge_summary_with_recent(result.summary, recent)

        for i, msg in enumerate(merged):
            if msg.role == "tool":
                assert msg.tool_call_id is not None
                assert any(
                    tc.id == msg.tool_call_id
                    for m in merged[:i]
                    if m.tool_calls
                    for tc in m.tool_calls
                )


class TestPolicyEngineAuthority:
    def test_tool_selection_does_not_bypass_policy(self):
        from security.policy_engine import PolicyEngine
        policy = PolicyEngine()
        tool = ToolMetadata(
            name="delete_file",
            description="Delete a file",
            security_level=SecurityLevel.RED,
            visibility=ToolVisibility.LOCAL_ONLY,
            parameters_schema={"type": "object", "properties": {}},
        )
        decision = policy.evaluate(tool, {"path": "/tmp/test"}, confirmed=False, source="orchestrator")
        assert not decision.allowed

    def test_tool_visibility_still_enforced(self):
        from security.policy_engine import PolicyEngine
        policy = PolicyEngine()
        tool = ToolMetadata(
            name="local_tool",
            description="Local only",
            security_level=SecurityLevel.GREEN,
            visibility=ToolVisibility.LOCAL_ONLY,
            parameters_schema={"type": "object", "properties": {}},
        )
        assert policy.evaluate_tool_visibility(tool, "mcp") is False
        assert policy.evaluate_tool_visibility(tool, "orchestrator") is True
