"""Central memory provider — SERVER-backed implementation of the memory interface.

Used by the CORE when central state is enabled, so memory reads/writes hit
the SERVER SQLite store instead of the local database. Failures raise
CentralStateError explicitly and are never masked with invented data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.contracts.memory import AuditEntry, BaseMemoryProvider, MemoryEntry
from core.logger import get_logger
from core.network.central_state_client import CentralStateClient, CentralStateError

logger = get_logger("jarvis.memory.central")


class CentralMemoryProvider(BaseMemoryProvider):
    """BaseMemoryProvider implemented over the central state HTTP API."""

    def __init__(self, central: CentralStateClient):
        if central is None:
            raise ValueError("CentralMemoryProvider requires a CentralStateClient.")
        self._central = central

    async def initialize(self) -> None:
        """No local schema to create; the SERVER owns the database."""
        return None

    async def set(self, key: str, value: Any, category: str = "general") -> None:
        await self._central.memory_set(key=key, value=value, category=category)

    async def get(self, key: str) -> Optional[MemoryEntry]:
        data = await self._central.memory_get(key)
        if data is None:
            return None
        return MemoryEntry(
            key=data["key"],
            value=data["value"],
            category=data.get("category", "general"),
            updated_at=datetime.now(timezone.utc),
        )

    async def delete(self, key: str) -> bool:
        return await self._central.memory_delete(key)

    async def list_by_category(self, category: str) -> List[MemoryEntry]:
        # The central API exposes search, not category listing; an empty
        # query would be a lie, so this backend reports unsupported instead
        # of inventing results. Search covers the tool's needs.
        raise CentralStateError(
            "Central memory does not expose category listing; use search instead.",
            kind="unsupported",
        )

    async def search_memory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search central memory; same shape as the SQLite provider."""
        return await self._central.memory_search(query=query, limit=limit)

    async def log_audit(self, entry: AuditEntry) -> None:
        raise CentralStateError(
            "Central memory does not accept audit writes from this backend.",
            kind="unsupported",
        )

    async def get_recent_audits(self, limit: int = 50) -> List[AuditEntry]:
        raise CentralStateError(
            "Central memory does not expose audit reads from this backend.",
            kind="unsupported",
        )
