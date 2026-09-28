"""Notification tools (Phase 15.1) — GREEN, store-first.

send_notification() persists through NotificationService and delivers via
the configured provider abstraction. No arbitrary URLs, no secrets in logs,
no fake deliveries: channels without a real provider stay pending with an
explicit reason.
"""

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from core.notifications.service import (
    CHANNELS,
    PRIORITIES,
    get_notification_service,
)


class SendNotificationArgs(BaseModel):
    title: str = Field(..., description="Short notification title")
    message: str = Field(..., description="Notification body")
    priority: str = Field(default="normal", description="One of: low, normal, high")
    channel: str = Field(default="push", description="One of: push, desktop, webhook")


class SendNotificationTool(BaseTool):
    """Store a notification and deliver it through the configured channel."""

    name: str = "send_notification"
    description: str = (
        "Store a notification and deliver it via push, desktop or webhook. "
        "Channels without an available provider stay pending explicitly."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = SendNotificationArgs
    # Title/message never reach a shell; priority/channel are validated enums.
    param_kinds: Dict[str, ParamKind] = {
        "title": ParamKind.FREE_TEXT,
        "message": ParamKind.FREE_TEXT,
        "priority": ParamKind.IDENT,
        "channel": ParamKind.IDENT,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            notification = await get_notification_service().create(
                title=kwargs.get("title", ""),
                message=kwargs.get("message", ""),
                priority=kwargs.get("priority", "normal"),
                channel=kwargs.get("channel", "push"),
            )
            return ToolResult.ok(data=notification, security_level=self.security_level)
        except ValueError as e:
            return ToolResult.fail(error=str(e), security_level=self.security_level)
        except Exception as e:
            return ToolResult.fail(
                error=f"Notification failed: {e.__class__.__name__}",
                security_level=self.security_level,
            )


class CheckPendingNotificationsTool(BaseTool):
    """List stored notifications that are still pending (read-only)."""

    name: str = "check_pending_notifications"
    description: str = "List pending (undelivered) notifications without changing their state."
    security_level: SecurityLevel = SecurityLevel.GREEN

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            pending = await get_notification_service().list_pending()
            return ToolResult.ok(
                data={"pending": pending, "count": len(pending)},
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(
                error=f"Could not list pending notifications: {e.__class__.__name__}",
                security_level=self.security_level,
            )
