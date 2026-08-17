"""Security Policy Engine intercepting all tool invocations."""

from typing import Any, Dict, Optional, Tuple
from core.contracts.enums import SecurityLevel
from core.contracts.tool import ToolMetadata
from core.config import get_settings
from security.allowlist import AllowlistValidator, SecurityValidationError


class PolicyDecision:
    """Outcome of a policy evaluation."""
    def __init__(self, allowed: bool, reason: str, requires_confirmation: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.requires_confirmation = requires_confirmation

    @classmethod
    def allow(cls, reason: str = "Authorized") -> "PolicyDecision":
        return cls(allowed=True, reason=reason, requires_confirmation=False)

    @classmethod
    def deny(cls, reason: str) -> "PolicyDecision":
        return cls(allowed=False, reason=reason, requires_confirmation=False)

    @classmethod
    def need_confirmation(cls, reason: str) -> "PolicyDecision":
        return cls(allowed=False, reason=reason, requires_confirmation=True)


class PolicyEngine:
    """Enforces safety, confirmation levels, and input parameter sanitization."""

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    def evaluate(
        self,
        tool: ToolMetadata,
        parameters: Dict[str, Any],
        confirmed: bool = False,
    ) -> PolicyDecision:
        """Evaluate whether a tool call is permitted according to safety rules."""
        settings = get_settings()

        # Step 1: Check parameter safety against shell injection / forbidden strings
        for param_name, param_val in parameters.items():
            if isinstance(param_val, str):
                try:
                    self.validator.sanitize_input_string(param_val)
                except SecurityValidationError as e:
                    return PolicyDecision.deny(f"Parameter '{param_name}' failed security sanitization: {e}")

        # Step 2: Check security levels
        if tool.security_level == SecurityLevel.GREEN:
            return PolicyDecision.allow("Action is classified GREEN and authorized automatically.")

        if tool.security_level == SecurityLevel.YELLOW:
            if settings.confirm_yellow_actions and not confirmed:
                return PolicyDecision.need_confirmation(
                    f"Tool '{tool.name}' is classified YELLOW (requires user confirmation before execution)."
                )
            return PolicyDecision.allow("Action is classified YELLOW and user confirmation was provided.")

        if tool.security_level == SecurityLevel.RED:
            if settings.confirm_red_actions and not confirmed:
                return PolicyDecision.need_confirmation(
                    f"Tool '{tool.name}' is classified RED (requires explicit high-privilege confirmation)."
                )
            return PolicyDecision.allow("Action is classified RED and explicit confirmation was provided.")

        return PolicyDecision.deny(f"Unknown security level for tool '{tool.name}'.")
