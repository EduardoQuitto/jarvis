"""Local notification store and provider abstraction (Phase 15.1)."""

from core.notifications.service import (
    CHANNELS,
    PRIORITIES,
    NotificationService,
    NotificationStatus,
    get_notification_service,
)

__all__ = [
    "CHANNELS",
    "PRIORITIES",
    "NotificationService",
    "NotificationStatus",
    "get_notification_service",
]
