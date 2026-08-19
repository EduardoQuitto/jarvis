"""Async Event Bus for publish/subscribe communication between components."""

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional

from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.events")

Callback = Callable[[SystemEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus for intra-system communication.

    Components subscribe to event types and receive callbacks when events are published.
    Events can also be collected by SSE endpoints for UI streaming.
    """

    def __init__(self, max_history: int = 200):
        self._subscribers: Dict[str, List[Callback]] = {}
        self._history: List[SystemEvent] = []
        self._max_history = max_history
        self._sse_queues: List[asyncio.Queue] = []

    def subscribe(self, event_type: EventType, callback: Callback) -> None:
        """Subscribe a callback to an event type."""
        key = event_type.value
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)
        logger.debug("Subscribed to %s", key)

    def subscribe_all(self, callback: Callback) -> None:
        """Subscribe to all event types."""
        for et in EventType:
            self.subscribe(et, callback)

    def unsubscribe(self, event_type: EventType, callback: Callback) -> None:
        """Unsubscribe a callback from an event type."""
        key = event_type.value
        if key in self._subscribers:
            self._subscribers[key] = [cb for cb in self._subscribers[key] if cb is not callback]

    async def publish(self, event: SystemEvent) -> None:
        """Publish an event to all subscribers and history."""
        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Notify type-specific subscribers
        key = event.event_type.value
        for callback in self._subscribers.get(key, []):
            try:
                await callback(event)
            except Exception as e:
                logger.error("Event callback error for %s: %s", key, str(e))

        # Notify wildcard subscribers
        for callback in self._subscribers.get("*", []):
            try:
                await callback(event)
            except Exception as e:
                logger.error("Wildcard callback error: %s", str(e))

        # Push to SSE queues
        for queue in self._sse_queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop if queue is full

    def get_history(self, limit: int = 50, event_type: Optional[EventType] = None) -> List[SystemEvent]:
        """Get recent events from history."""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def create_sse_queue(self) -> asyncio.Queue:
        """Create a new queue for SSE streaming. Caller is responsible for consuming."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._sse_queues.append(queue)
        return queue

    def remove_sse_queue(self, queue: asyncio.Queue) -> None:
        """Remove an SSE queue."""
        self._sse_queues = [q for q in self._sse_queues if q is not queue]

    @property
    def subscriber_count(self) -> int:
        return sum(len(cbs) for cbs in self._subscribers.values())


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Access the global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
