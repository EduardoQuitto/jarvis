"""Allowlist and path sandboxing enforcement."""

import os
from pathlib import Path
from typing import Dict, List, Optional
import re

from core.config import get_settings


class SecurityValidationError(Exception):
    """Raised when an operation violates security policy or sandbox boundaries."""
    pass


class AllowlistValidator:
    """Validates application execution and filesystem operations against strict allowlists."""

    # Disallowed dangerous shell characters to prevent injection attacks
    DANGEROUS_CHARS_REGEX = re.compile(r"[\;&\|><`\$\(\)\{\}\n\r]")

    def __init__(self, allowed_apps: Optional[Dict[str, str]] = None, allowed_paths: Optional[List[str]] = None):
        settings = get_settings()
        self.allowed_apps = allowed_apps if allowed_apps is not None else settings.allowed_apps
        self.allowed_paths = allowed_paths if allowed_paths is not None else settings.allowed_paths

    def sanitize_input_string(self, text: str) -> str:
        """Ensure input contains no shell metacharacters or dangerous control codes."""
        if self.DANGEROUS_CHARS_REGEX.search(text):
            raise SecurityValidationError(f"Input string contains forbidden characters: {text!r}")
        return text.strip()

    def get_allowed_executable(self, app_alias_or_name: str) -> str:
        """Resolve a friendly application name to its approved executable name."""
        clean_name = self.sanitize_input_string(app_alias_or_name).lower()
        
        # Check direct alias
        if clean_name in self.allowed_apps:
            return self.allowed_apps[clean_name]
            
        # Check if full exe name is in values
        for alias, exe_name in self.allowed_apps.items():
            if clean_name == exe_name.lower():
                return exe_name
                
        raise SecurityValidationError(
            f"Application '{app_alias_or_name}' is not in the approved allowlist. Allowed apps: {list(self.allowed_apps.keys())}"
        )

    def validate_file_path(self, target_path: str, must_exist: bool = False) -> Path:
        """Ensure the target filesystem path is safely within allowed root directories."""
        self.sanitize_input_string(target_path)
        
        resolved_path = Path(target_path).resolve()
        
        if must_exist and not resolved_path.exists():
            raise SecurityValidationError(f"Target path does not exist: {target_path}")

        # Check if resolved path is contained within any allowed root
        is_safe = False
        for allowed_root in self.allowed_paths:
            resolved_root = Path(allowed_root).resolve()
            try:
                # relative_to will raise ValueError if resolved_path is not inside resolved_root
                resolved_path.relative_to(resolved_root)
                is_safe = True
                break
            except ValueError:
                continue

        if not is_safe:
            raise SecurityValidationError(
                f"Path '{target_path}' is outside sandbox boundaries. Allowed directories: {self.allowed_paths}"
            )

        return resolved_path
