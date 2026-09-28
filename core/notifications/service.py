"""Notification store with a small provider abstraction.

Architecture:
    send_notification() -> NotificationService -> provider -> channel

Providers available today:
- "push": NO real provider exists in this project (no mobile/ADB
  infrastructure). Notifications persist as pending/queued with an explicit
  message naming what is missing. Nothing is faked as delivered.
- "desktop": no multiplatform mechanism without new dependencies, so it
  behaves like push (pending + documented reason).
- "webhook": POSTs to the single destination configured via
  JARVIS_NOTIFICATION_WEBHOOK_URL. Never to a caller-supplied URL.

Persistence uses the runtime memory backend (local SQLite or central
store) under keys "notification:{id}" plus a "notification:index" id list,
so listing works on every backend. No secrets are ever logged: only the
notification id, channel and status reach the logs.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.logger import get_logger
from memory import get_memory_provider

logger = get_logger("jarvis.notifications")

PRIORITIES = ("low", "normal", "high")
CHANNELS = ("push", "desktop", "webhook")

_INDEX_KEY = "notification:index"
_KEY_PREFIX = "notification:"
_CATEGORY = "notifications"


class NotificationStatus:
    """Lifecycle of a stored notification."""
    PENDING = "pending"      # stored, awaiting a capable provider
    DELIVERED = "delivered"  # a provider confirmed delivery
    FAILED = "failed"        # delivery attempted and failed explicitly


class QueuedProvider:
    """Placeholder provider: stores as pending, never claims delivery."""

    def __init__(self, reason: str):
        self.reason = reason

    async def deliver(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        return {"delivered": False, "pending": True, "reason": self.reason}


class WebhookProvider:
    """POSTs to the single server-configured webhook destination."""

    def __init__(self, url: str, timeout: float = 10.0, transport=None):
        self._url = url
        self._timeout = timeout
        self._transport = transport

    async def deliver(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "notification_id": notification["notification_id"],
            "title": notification["title"],
            "message": notification["message"],
            "priority": notification["priority"],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._url, json=payload)
        except httpx.TimeoutException as e:
            return {"delivered": False, "error": f"webhook timeout: {e.__class__.__name__}"}
        except (httpx.ConnectError, httpx.NetworkError) as e:
            return {"delivered": False, "error": f"webhook unreachable: {e.__class__.__name__}"}
        except Exception as e:
            return {"delivered": False, "error": f"webhook transport error: {e.__class__.__name__}"}
        if 200 <= response.status_code < 300:
            return {"delivered": True}
        return {"delivered": False, "error": f"webhook HTTP {response.status_code}"}


class NotificationService:
    """Creates, stores and lists notifications; delivers via providers."""

    def __init__(self, memory=None, webhook_transport=None):
        self._memory = memory
        self._webhook_transport = webhook_transport

    def _get_memory(self):
        if self._memory is None:
            self._memory = get_memory_provider()
        return self._memory

    def _provider_for(self, channel: str):
        if channel == "webhook":
            url = get_settings().notification_webhook_url
            if not url:
                return None
            return WebhookProvider(url, transport=self._webhook_transport)
        if channel == "push":
            return QueuedProvider(
                "no push provider configured: mobile/ADB infrastructure not available; "
                "notification stored as pending"
            )
        return QueuedProvider(
            "no desktop provider available without new multiplatform dependencies; "
            "notification stored as pending"
        )

    async def _load_index(self) -> List[str]:
        memory = self._get_memory()
        entry = await memory.get(_INDEX_KEY)
        if entry is None:
            return []
        return list(entry.value) if isinstance(entry.value, list) else []

    async def _save_index(self, ids: List[str]) -> None:
        await self._get_memory().set(_INDEX_KEY, ids, category=_CATEGORY)

    async def create(
        self,
        title: str,
        message: str,
        priority: str = "normal",
        channel: str = "push",
    ) -> Dict[str, Any]:
        """Validate, persist as pending, then attempt delivery via provider."""
        if priority not in PRIORITIES:
            raise ValueError(f"Invalid priority {priority!r}. Expected one of {PRIORITIES}.")
        if channel not in CHANNELS:
            raise ValueError(f"Invalid channel {channel!r}. Expected one of {CHANNELS}.")
        notification_id = f"notif-{uuid.uuid4().hex[:12]}"
        now = time.time()
        notification = {
            "notification_id": notification_id,
            "title": title,
            "message": message,
            "priority": priority,
            "channel": channel,
            "created_at": now,
            "delivered_at": None,
            "status": NotificationStatus.PENDING,
            "error": None,
        }
        memory = self._get_memory()
        await memory.set(_KEY_PREFIX + notification_id, notification, category=_CATEGORY)
        index = await self._load_index()
        if notification_id not in index:
            index.append(notification_id)
            await self._save_index(index)

        provider = self._provider_for(channel)
        if provider is None:
            notification["status"] = NotificationStatus.FAILED
            notification["error"] = "no webhook destination configured (JARVIS_NOTIFICATION_WEBHOOK_URL is empty)"
            await memory.set(_KEY_PREFIX + notification_id, notification, category=_CATEGORY)
            logger.warning("notification %s failed: no webhook configured", notification_id)
            return notification

        outcome = await provider.deliver(notification)
        if outcome.get("delivered"):
            notification["status"] = NotificationStatus.DELIVERED
            notification["delivered_at"] = time.time()
            logger.info("notification %s delivered via %s", notification_id, channel)
        elif outcome.get("pending"):
            logger.info("notification %s queued as pending (%s)", notification_id, channel)
        else:
            notification["status"] = NotificationStatus.FAILED
            notification["error"] = outcome.get("error", "delivery failed")
            logger.warning("notification %s failed via %s", notification_id, channel)
        await memory.set(_KEY_PREFIX + notification_id, notification, category=_CATEGORY)
        return notification

    async def get(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one notification by id (None when unknown)."""
        entry = await self._get_memory().get(_KEY_PREFIX + notification_id)
        return dict(entry.value) if entry is not None else None

    async def list_pending(self) -> List[Dict[str, Any]]:
        """List pending notifications in creation order. Never mutates state."""
        memory = self._get_memory()
        pending = []
        for notification_id in await self._load_index():
            entry = await memory.get(_KEY_PREFIX + notification_id)
            if entry is not None and entry.value.get("status") == NotificationStatus.PENDING:
                pending.append(dict(entry.value))
        return pending


_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Access the shared notification service instance."""
    global _service
    if _service is None:
        _service = NotificationService()
    return _service
