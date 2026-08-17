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
