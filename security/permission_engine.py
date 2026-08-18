"""Permission Engine implementing fine-grained security policies and decisions."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import ToolMetadata
from core.config import get_settings
from security.allowlist import AllowlistValidator, SecurityValidationError


class PermissionStatus(str, Enum):
    """Possible outcomes of a permission check."""
    ALLOW = "ALLOW"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    DENY = "DENY"


class PermissionDecision(BaseModel):
    """Detailed result of a permission evaluation."""
    status: PermissionStatus
    reason: str
    level: SecurityLevel
    requires_confirmation: bool = False

    @property
    def is_allowed(self) -> bool:
        return self.status == PermissionStatus.ALLOW

    @classmethod
    def allow(cls, level: SecurityLevel, reason: str = "Action authorized") -> "PermissionDecision":
        return cls(
            status=PermissionStatus.ALLOW,
            reason=reason,
            level=level,
            requires_confirmation=False,
        )

    @classmethod
    def require_confirmation(cls, level: SecurityLevel, reason: str) -> "PermissionDecision":
        return cls(
            status=PermissionStatus.REQUIRE_CONFIRMATION,
            reason=reason,
            level=level,
            requires_confirmation=True,
        )

    @classmethod
    def deny(cls, level: SecurityLevel, reason: str) -> "PermissionDecision":
        return cls(
            status=PermissionStatus.DENY,
            reason=reason,
            level=level,
            requires_confirmation=False,
        )


class PermissionEngine:
    """Evaluates security permissions before executing tools and operations."""

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    def evaluate(
        self,
        tool: ToolMetadata,
        parameters: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        confirmation_token: Optional[str] = None,
    ) -> PermissionDecision:
        """Evaluate whether a tool invocation is permitted."""
        parameters = parameters or {}
        settings = get_settings()

        # Step 1: Input sanitization check across all parameters
        for param_name, param_val in parameters.items():
            if isinstance(param_val, str):
                try:
                    self.validator.sanitize_input_string(param_val)
                except SecurityValidationError as se:
                    return PermissionDecision.deny(
                        level=tool.security_level,
                        reason=f"Parameter '{param_name}' failed security sanitization: {se}",
                    )

        # Step 2: GREEN Level — Automatically allowed
        if tool.security_level == SecurityLevel.GREEN:
            return PermissionDecision.allow(
                level=SecurityLevel.GREEN,
                reason="GREEN level action authorized automatically.",
            )

        # Step 3: YELLOW Level — Requires user confirmation
        if tool.security_level == SecurityLevel.YELLOW:
            if settings.confirm_yellow_actions and not confirmed:
                return PermissionDecision.require_confirmation(
                    level=SecurityLevel.YELLOW,
                    reason=f"Tool '{tool.name}' is classified YELLOW and requires user confirmation.",
                )
            return PermissionDecision.allow(
                level=SecurityLevel.YELLOW,
                reason="YELLOW level action confirmed and authorized.",
            )

        # Step 4: RED Level — Requires explicit high-privilege confirmation
        if tool.security_level == SecurityLevel.RED:
            if settings.confirm_red_actions and not confirmed:
                return PermissionDecision.require_confirmation(
                    level=SecurityLevel.RED,
                    reason=f"Tool '{tool.name}' is classified RED and requires explicit authorization.",
                )
            return PermissionDecision.allow(
                level=SecurityLevel.RED,
                reason="RED level action explicitly authorized.",
            )

        return PermissionDecision.deny(
            level=tool.security_level,
            reason=f"Unknown security level for tool '{tool.name}'.",
        )
