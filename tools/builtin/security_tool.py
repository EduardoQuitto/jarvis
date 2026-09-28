"""Security utility tools (Phase 15.1) — GREEN, local computation only.

- Passwords use secrets (never random, never logged, never persisted).
- Hashing uses hashlib with an explicit allowlist; MD5/SHA-1 exist only for
  compatibility/integrity checks, never as a security recommendation.
- Files stream in chunks and stay inside the sandbox (PATH semantics).
"""

import hashlib
import hmac
import secrets
import string
from pathlib import Path
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from security.allowlist import AllowlistValidator, SecurityValidationError

_HASH_CHUNK_BYTES = 65536
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128

# Explicit allowlist: dynamic getattr(hashlib, name) on user input is forbidden.
_HASH_ALGORITHMS = ("sha256", "sha512", "sha1", "md5")
# Expected hex lengths, used by verify_checksum's documented "auto" mode.
_HASH_HEX_LENGTHS = {"sha256": 64, "sha512": 128, "sha1": 40, "md5": 32}

_PASSWORD_ALPHABETS = {
    "low": string.ascii_lowercase + string.digits,
    # medium/high add classes below; ambiguous lookalikes (l, 1, I, 0, O)
    # are intentionally KEPT to maximize entropy — documented choice.
    "medium": string.ascii_lowercase + string.ascii_uppercase + string.digits,
    "high": string.ascii_letters + string.digits + string.punctuation,
}
_PASSWORD_REQUIRED_CLASSES = {
    "low": (string.ascii_lowercase,),
    "medium": (string.ascii_lowercase, string.ascii_uppercase, string.digits),
    "high": (string.ascii_lowercase, string.ascii_uppercase, string.digits, string.punctuation),
}


def _hash_file(path: Path, algorithm: str) -> tuple:
    """Hash a file in chunks. Returns (hex_digest, size_bytes)."""
    digest = hashlib.new(algorithm)
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


class GeneratePasswordArgs(BaseModel):
    length: int = Field(default=16, description="Password length (8-128)")
    complexity: str = Field(default="high", description="One of: low, medium, high")


class GeneratePasswordTool(BaseTool):
    """Generate a cryptographically secure random password (never stored)."""

    name: str = "generate_password"
    description: str = "Generate a secure random password with the given length and complexity."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = GeneratePasswordArgs
    param_kinds: Dict[str, ParamKind] = {"complexity": ParamKind.IDENT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            length = int(kwargs.get("length", 16))
        except (TypeError, ValueError):
            return ToolResult.fail(
                error=f"Invalid length: {kwargs.get('length')!r}. Expected an integer 8-128.",
                security_level=self.security_level,
            )
        if not _PASSWORD_MIN_LENGTH <= length <= _PASSWORD_MAX_LENGTH:
            return ToolResult.fail(
                error=f"Invalid length: {length}. Expected 8-128.",
                security_level=self.security_level,
            )
        complexity = kwargs.get("complexity", "high")
        if complexity not in _PASSWORD_ALPHABETS:
            return ToolResult.fail(
                error=f"Invalid complexity: {complexity!r}. Expected one of low, medium, high.",
                security_level=self.security_level,
            )
        alphabet = _PASSWORD_ALPHABETS[complexity]
        # Guarantee at least one character from each required class.
        required = [secrets.choice(cls) for cls in _PASSWORD_REQUIRED_CLASSES[complexity]]
        rest = [secrets.choice(alphabet) for _ in range(length - len(required))]
        password = "".join(required + rest)
        # Shuffle without random module (Fisher-Yates with secrets).
        chars = list(password)
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return ToolResult.ok(
            data={"password": "".join(chars), "length": length, "complexity": complexity},
            security_level=self.security_level,
        )


class HashFileArgs(BaseModel):
    file_path: str = Field(..., description="File to hash (inside sandbox)")
    algorithm: str = Field(default="sha256", description="One of: sha256, sha512, sha1, md5")


class HashFileTool(BaseTool):
    """Hash a file with an explicitly allowlisted algorithm (chunked)."""

    name: str = "hash_file"
    description: str = "Compute the cryptographic hash of a file. MD5/SHA-1 are integrity-only, not security recommendations."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = HashFileArgs
    param_kinds: Dict[str, ParamKind] = {
        "file_path": ParamKind.PATH,
        "algorithm": ParamKind.IDENT,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        algorithm = kwargs.get("algorithm", "sha256")
        if algorithm not in _HASH_ALGORITHMS:
            return ToolResult.fail(
                error=f"Invalid algorithm: {algorithm!r}. Allowed: {', '.join(_HASH_ALGORITHMS)}.",
                security_level=self.security_level,
            )
        validator = AllowlistValidator()
        try:
            resolved = validator.validate_sandbox_path(kwargs.get("file_path", ""))
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )
        if not resolved.is_file():
            return ToolResult.fail(
                error=f"Not a file: {kwargs.get('file_path')}",
                security_level=self.security_level,
            )
        try:
            hex_digest, size = _hash_file(resolved, algorithm)
        except OSError as e:
            return ToolResult.fail(
                error=f"Cannot read file: {e}",
                security_level=self.security_level,
            )
        return ToolResult.ok(
            data={
                "file_path": str(resolved),
                "algorithm": algorithm,
                "hash_hex": hex_digest,
                "size_bytes": size,
            },
            security_level=self.security_level,
        )


class VerifyChecksumArgs(BaseModel):
    file_path: str = Field(..., description="File to verify (inside sandbox)")
    expected_hash: str = Field(..., description="Expected hex digest")
    algorithm: str = Field(default="sha256", description="Explicit algorithm, or 'auto' to infer from hex length (documented)")


class VerifyChecksumTool(BaseTool):
    """Verify a file against an expected hex digest (constant-time compare)."""

    name: str = "verify_checksum"
    description: str = "Verify a file checksum. Prefer an explicit algorithm; 'auto' infers only from documented hex lengths (64/128/40/32)."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = VerifyChecksumArgs
    param_kinds: Dict[str, ParamKind] = {
        "file_path": ParamKind.PATH,
        "expected_hash": ParamKind.IDENT,
        "algorithm": ParamKind.IDENT,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        expected = kwargs.get("expected_hash", "")
        if not isinstance(expected, str):
            return ToolResult.fail(
                error="expected_hash must be a hex string.",
                security_level=self.security_level,
            )
        expected = expected.strip().lower()
        algorithm = kwargs.get("algorithm", "sha256")
        if algorithm == "auto":
            matches = [name for name, size in _HASH_HEX_LENGTHS.items() if size == len(expected)]
            if len(matches) != 1:
                return ToolResult.fail(
                    error=f"Cannot infer algorithm from hex length {len(expected)}. "
                          f"Use an explicit algorithm: {', '.join(_HASH_ALGORITHMS)}.",
                    security_level=self.security_level,
                )
            algorithm = matches[0]
        if algorithm not in _HASH_ALGORITHMS:
            return ToolResult.fail(
                error=f"Invalid algorithm: {algorithm!r}. Allowed: {', '.join(_HASH_ALGORITHMS)}.",
                security_level=self.security_level,
            )
        if len(expected) != _HASH_HEX_LENGTHS[algorithm] or any(
            c not in "0123456789abcdef" for c in expected
        ):
            return ToolResult.fail(
                error=f"expected_hash is not valid {_HASH_HEX_LENGTHS[algorithm]}-char hex for {algorithm}.",
                security_level=self.security_level,
            )
        validator = AllowlistValidator()
        try:
            resolved = validator.validate_sandbox_path(kwargs.get("file_path", ""))
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )
        if not resolved.is_file():
            return ToolResult.fail(
                error=f"Not a file: {kwargs.get('file_path')}",
                security_level=self.security_level,
            )
        try:
            actual, _ = _hash_file(resolved, algorithm)
        except OSError as e:
            return ToolResult.fail(
                error=f"Cannot read file: {e}",
                security_level=self.security_level,
            )
        return ToolResult.ok(
            data={
                "file_path": str(resolved),
                "algorithm": algorithm,
                "actual_hash": actual,
                "expected_hash": expected,
                "matches": hmac.compare_digest(actual, expected),
            },
            security_level=self.security_level,
        )
