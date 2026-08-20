"""Shared test fixtures and cleanup for JARVIS test suite."""

import warnings

import pytest


@pytest.fixture(autouse=True)
def _suppress_aiosqlite_thread_warnings():
    """Suppress aiosqlite background thread warnings during test teardown.

    aiosqlite uses a background thread for SQLite I/O. When the asyncio event loop
    closes at test teardown, the thread may still be running and emit warnings.
    This is harmless — the thread will finish on its own.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        yield
