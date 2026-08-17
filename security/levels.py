"""Security levels and validation helpers."""

from core.contracts.enums import SecurityLevel


def is_action_allowed_automatically(level: SecurityLevel) -> bool:
    """Returns True if the action belongs to the GREEN level and requires no confirmation."""
    return level == SecurityLevel.GREEN


def requires_user_confirmation(level: SecurityLevel) -> bool:
    """Returns True if action is YELLOW or RED requiring authorization."""
    return level in (SecurityLevel.YELLOW, SecurityLevel.RED)
