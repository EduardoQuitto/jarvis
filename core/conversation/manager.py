"""Conversation Manager — session lifecycle, message persistence, context window management."""

import json
import uuid
from typing import Dict, List, Optional

from core.contracts.llm import LLMMessage, LLMToolCall
from core.contracts.conversation import ConversationMessage, ConversationSession
from memory.sqlite_provider import SQLiteMemoryProvider
from core.logger import get_logger

logger = get_logger("jarvis.conversation")


class ConversationManager:
    """Manages conversation sessions, persists messages, and provides context windows."""

    def __init__(self, memory: Optional[SQLiteMemoryProvider] = None, max_context_messages: int = 40):
        self._memory = memory
        self._max_context = max_context_messages
        self._local_sessions: Dict[str, List[ConversationMessage]] = {}

    def _get_memory(self) -> SQLiteMemoryProvider:
        if self._memory is None:
            self._memory = SQLiteMemoryProvider()
        return self._memory

    async def create_session(
        self,
        title: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> str:
        """Create a new conversation session and return its ID."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        try:
            mem = self._get_memory()
            await mem.create_conversation(session_id, title=title, device_id=device_id)
        except Exception as e:
            logger.warning("Failed to persist conversation: %s — using local fallback", e)
            self._local_sessions[session_id] = []
        logger.info("Created conversation session: %s", session_id)
        return session_id

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls_json: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """Append a message to a conversation session."""
        msg = ConversationMessage(
            conversation_id=session_id,
            role=role,
            content=content,
            tool_calls_json=tool_calls_json,
            tool_call_id=tool_call_id,
            name=name,
        )
        try:
            mem = self._get_memory()
            await mem.append_conversation_message(
                session_id, role, content,
                tool_calls_json=tool_calls_json,
                tool_call_id=tool_call_id,
                name=name,
            )
        except Exception as e:
            logger.warning("Failed to persist message: %s", e)
            if session_id not in self._local_sessions:
                self._local_sessions[session_id] = []
            self._local_sessions[session_id].append(msg)

    async def get_history(self, session_id: str, limit: int = 50) -> List[ConversationMessage]:
        """Retrieve conversation history as ConversationMessage objects."""
        try:
            mem = self._get_memory()
            rows = await mem.get_conversation_history(session_id, limit=limit)
            return [
                ConversationMessage(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    role=row["role"],
                    content=row["content"],
                    tool_calls_json=row["tool_calls_json"],
                    tool_call_id=row["tool_call_id"],
                    name=row["name"],
                )
                for row in rows
            ]
        except Exception:
            return self._local_sessions.get(session_id, [])[-limit:]

    async def get_context_window(self, session_id: str) -> List[LLMMessage]:
        """Get the conversation as LLMMessage objects for the context window.

        Applies the sliding window: keeps the most recent messages within max_context.
        """
        history = await self.get_history(session_id, limit=self._max_context)
        llm_messages = []
        for msg in history:
            tool_calls = None
            if msg.tool_calls_json:
                try:
                    parsed = json.loads(msg.tool_calls_json)
                    tool_calls = [LLMToolCall.model_validate(tc) for tc in parsed]
                except (json.JSONDecodeError, Exception):
                    tool_calls = None
            llm_messages.append(
                LLMMessage(
                    role=msg.role,
                    content=msg.content or "",
                    tool_calls=tool_calls,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            )
        return llm_messages

    async def list_sessions(self, limit: int = 20) -> List[ConversationSession]:
        """List recent conversation sessions."""
        try:
            mem = self._get_memory()
            rows = await mem.list_conversations(limit=limit)
            return [
                ConversationSession(
                    id=row["id"],
                    title=row["title"],
                    task_id=row["task_id"],
                    device_id=row["device_id"],
                    message_count=row["message_count"],
                )
                for row in rows
            ]
        except Exception:
            return []

    async def get_session_info(self, session_id: str) -> Optional[ConversationSession]:
        """Get info about a specific session."""
        try:
            mem = self._get_memory()
            async with mem._get_connection() as conn:
                async with conn.execute(
                    "SELECT id, title, task_id, device_id, created_at, updated_at, message_count FROM conversations WHERE id = ?",
                    (session_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return ConversationSession(
                            id=row["id"],
                            title=row["title"],
                            task_id=row["task_id"],
                            device_id=row["device_id"],
                            message_count=row["message_count"],
                        )
        except Exception:
            pass
        return None
