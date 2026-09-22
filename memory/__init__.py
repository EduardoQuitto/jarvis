"""Memory package."""

from core.network.central_state_client import CentralStateClient
from memory.central_provider import CentralMemoryProvider
from memory.sqlite_provider import SQLiteMemoryProvider


def get_memory_provider():
    """Return the runtime memory backend.

    Central SERVER store when JARVIS_CENTRAL_STATE_ENABLED is set,
    otherwise the local SQLite provider (existing behavior).
    """
    central = CentralStateClient.from_settings()
    if central is not None:
        return CentralMemoryProvider(central=central)
    return SQLiteMemoryProvider()


__all__ = ["SQLiteMemoryProvider", "CentralMemoryProvider", "get_memory_provider"]
