"""Async SQLite Memory Provider implementation for persistent state and audit trails."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import aiosqlite

from core.contracts.enums import SecurityLevel
from core.contracts.memory import AuditEntry, BaseMemoryProvider, MemoryEntry
from core.config import get_settings


class SQLiteMemoryProvider(BaseMemoryProvider):
    """SQLite-backed asynchronous storage engine for memory, key-value state and audit logs."""

    def __init__(self, db_path: Optional[str] = None):
        settings = get_settings()
        self.db_path = db_path or settings.db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def _get_connection(self) -> aiosqlite.Connection:
        if self._db is None:
            # Ensure directory exists
            parent_dir = Path(self.db_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._init_tables()
        return self._db

    async def initialize(self) -> None:
        """Initialize connection and schema."""
        await self._get_connection()

    async def _init_tables(self) -> None:
        if self._db is None:
            return

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                node_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                security_level TEXT NOT NULL,
                parameters TEXT NOT NULL,
                success INTEGER NOT NULL,
                error TEXT,
                duration_ms REAL NOT NULL DEFAULT 0.0
            )
        """)

        # Conversations table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                task_id TEXT,
                device_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Conversation messages table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tool_calls_json TEXT,
                tool_call_id TEXT,
                name TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_messages_conv_id
            ON conversation_messages(conversation_id)
        """)

        # Tasks table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'PENDING',
                plan_id TEXT,
                conversation_id TEXT,
                device_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                current_step TEXT,
                progress_pct REAL NOT NULL DEFAULT 0.0,
                total_steps INTEGER NOT NULL DEFAULT 0,
                completed_steps INTEGER NOT NULL DEFAULT 0,
                result TEXT,
                errors TEXT NOT NULL DEFAULT '[]',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                waiting_reason TEXT
            )
        """)

        # Task checkpoints table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS task_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                step_description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                result_json TEXT,
                error TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """)

        # Devices table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                device_type TEXT NOT NULL DEFAULT 'UNKNOWN',
                status TEXT NOT NULL DEFAULT 'OFFLINE',
                capabilities TEXT NOT NULL DEFAULT '[]',
                version TEXT NOT NULL DEFAULT '0.1.0',
                ip_address TEXT,
                port INTEGER,
                last_seen TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)

        # Events table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'system',
                data TEXT NOT NULL DEFAULT '{}',
                timestamp TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(event_type)
        """)

        await self._db.commit()

    async def set(self, key: str, value: Any, category: str = "general") -> None:
        """Store or update a key-value record."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        serialized_val = json.dumps(value)

        await db.execute(
            """
            INSERT INTO memory_store (key, value, category, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                updated_at = excluded.updated_at
            """,
            (key, serialized_val, category, now_str),
        )
        await db.commit()

    async def get(self, key: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by key."""
        db = await self._get_connection()
        async with db.execute("SELECT key, value, category, updated_at FROM memory_store WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return MemoryEntry(
                key=row["key"],
                value=json.loads(row["value"]),
                category=row["category"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        db = await self._get_connection()
        cursor = await db.execute("DELETE FROM memory_store WHERE key = ?", (key,))
        await db.commit()
        return cursor.rowcount > 0

    async def list_by_category(self, category: str) -> List[MemoryEntry]:
        """List all entries matching a category."""
        db = await self._get_connection()
        async with db.execute("SELECT key, value, category, updated_at FROM memory_store WHERE category = ?", (category,)) as cursor:
            rows = await cursor.fetchall()
            return [
                MemoryEntry(
                    key=row["key"],
                    value=json.loads(row["value"]),
                    category=row["category"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]

    async def log_audit(self, entry: AuditEntry) -> None:
        """Persist an audit trail entry."""
        db = await self._get_connection()
        await db.execute(
            """
            INSERT INTO audit_logs (timestamp, node_id, tool_name, security_level, parameters, success, error, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(),
                entry.node_id,
                entry.tool_name,
                entry.security_level.value,
                json.dumps(entry.parameters),
                1 if entry.success else 0,
                entry.error,
                entry.duration_ms,
            ),
        )
        await db.commit()

    async def get_recent_audits(self, limit: int = 50) -> List[AuditEntry]:
        """Fetch recent audit entries in descending chronological order."""
        db = await self._get_connection()
        async with db.execute(
            "SELECT id, timestamp, node_id, tool_name, security_level, parameters, success, error, duration_ms FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                AuditEntry(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    node_id=row["node_id"],
                    tool_name=row["tool_name"],
                    security_level=SecurityLevel(row["security_level"]),
                    parameters=json.loads(row["parameters"]),
                    success=bool(row["success"]),
                    error=row["error"],
                    duration_ms=row["duration_ms"],
                )
                for row in rows
            ]

    async def close(self) -> None:
        """Close active database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # --- Conversation methods ---

    async def create_conversation(self, conversation_id: str, title: str = None, device_id: str = None) -> None:
        """Create a new conversation session."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO conversations (id, title, device_id, created_at, updated_at, message_count) VALUES (?, ?, ?, ?, ?, 0)",
            (conversation_id, title, device_id, now_str, now_str),
        )
        await db.commit()

    async def append_conversation_message(
        self, conversation_id: str, role: str, content: str,
        tool_calls_json: str = None, tool_call_id: str = None, name: str = None,
    ) -> None:
        """Append a message to a conversation."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO conversation_messages (conversation_id, role, content, tool_calls_json, tool_call_id, name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, tool_calls_json, tool_call_id, name, now_str),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
            (now_str, conversation_id),
        )
        await db.commit()

    async def get_conversation_history(self, conversation_id: str, limit: int = 50) -> list:
        """Get messages from a conversation, oldest first."""
        db = await self._get_connection()
        async with db.execute(
            "SELECT id, conversation_id, role, content, tool_calls_json, tool_call_id, name, created_at FROM conversation_messages WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
            (conversation_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "conversation_id": row["conversation_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "tool_calls_json": row["tool_calls_json"],
                    "tool_call_id": row["tool_call_id"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    async def list_conversations(self, limit: int = 20) -> list:
        """List conversation sessions."""
        db = await self._get_connection()
        async with db.execute(
            "SELECT id, title, task_id, device_id, created_at, updated_at, message_count FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # --- Task methods ---

    async def create_task(self, task_id: str, objective: str, context: str = "{}",
                          priority: str = "normal", conversation_id: str = None, device_id: str = None) -> None:
        """Create a new task."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO tasks (task_id, objective, context, priority, status, conversation_id, device_id, created_at, updated_at, errors)
               VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, '[]')""",
            (task_id, objective, context, priority, conversation_id, device_id, now_str, now_str),
        )
        await db.commit()

    async def update_task(self, task_id: str, **fields) -> None:
        """Update task fields. Supported: status, result, waiting_reason, current_step,
        progress_pct, total_steps, completed_steps, retry_count, errors, started_at, completed_at."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        fields["updated_at"] = now_str
        set_parts = []
        values = []
        for k, v in fields.items():
            if v is not None:
                set_parts.append(f"{k} = ?")
                values.append(v)
        if not set_parts:
            return
        values.append(task_id)
        await db.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE task_id = ?", values)
        await db.commit()

    async def get_task(self, task_id: str) -> dict:
        """Get a task by ID."""
        db = await self._get_connection()
        async with db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_tasks(self, status: str = None, limit: int = 50) -> list:
        """List tasks, optionally filtered by status."""
        db = await self._get_connection()
        if status:
            async with db.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def add_task_checkpoint(self, task_id: str, step_id: str, step_description: str,
                                  status: str, result_json: str = None, error: str = None) -> None:
        """Add a checkpoint for a task step."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO task_checkpoints (task_id, step_id, step_description, status, result_json, error, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, step_id, step_description, status, result_json, error, now_str),
        )
        await db.commit()

    async def get_task_checkpoints(self, task_id: str) -> list:
        """Get all checkpoints for a task."""
        db = await self._get_connection()
        async with db.execute(
            "SELECT * FROM task_checkpoints WHERE task_id = ? ORDER BY id ASC", (task_id,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    # --- Device methods ---

    async def register_device(self, device_id: str, name: str, device_type: str,
                              status: str, capabilities: str, version: str,
                              ip_address: str = None, port: int = None, metadata: str = "{}") -> None:
        """Register or update a device."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO devices (device_id, name, device_type, status, capabilities, version, ip_address, port, last_seen, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(device_id) DO UPDATE SET
               name=excluded.name, device_type=excluded.device_type, status=excluded.status,
               capabilities=excluded.capabilities, version=excluded.version,
               ip_address=excluded.ip_address, port=excluded.port, last_seen=excluded.last_seen,
               metadata=excluded.metadata""",
            (device_id, name, device_type, status, capabilities, version, ip_address, port, now_str, metadata),
        )
        await db.commit()

    async def update_device_heartbeat(self, device_id: str, status: str = "ONLINE") -> None:
        """Update device heartbeat timestamp."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE devices SET last_seen = ?, status = ? WHERE device_id = ?",
            (now_str, status, device_id),
        )
        await db.commit()

    async def get_device(self, device_id: str) -> dict:
        """Get a device by ID."""
        db = await self._get_connection()
        async with db.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_devices(self) -> list:
        """List all registered devices."""
        db = await self._get_connection()
        async with db.execute("SELECT * FROM devices ORDER BY last_seen DESC") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    # --- Event methods ---

    async def log_event(self, event_type: str, source: str = "system", data: str = "{}") -> None:
        """Log a system event."""
        db = await self._get_connection()
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO events (event_type, source, data, timestamp) VALUES (?, ?, ?, ?)",
            (event_type, source, data, now_str),
        )
        await db.commit()

    async def get_recent_events(self, limit: int = 50, event_type: str = None) -> list:
        """Get recent events, optionally filtered by type."""
        db = await self._get_connection()
        if event_type:
            async with db.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                (event_type, limit),
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    # --- Search methods ---

    async def search_memory(self, query: str, limit: int = 10) -> list:
        """Search memory entries by key or value content."""
        db = await self._get_connection()
        search_term = f"%{query}%"
        async with db.execute(
            "SELECT key, value, category, updated_at FROM memory_store WHERE key LIKE ? OR value LIKE ? LIMIT ?",
            (search_term, search_term, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"key": row["key"], "value": json.loads(row["value"]), "category": row["category"]}
                for row in rows
            ]
