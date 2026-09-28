"""Filesystem analysis tools (Phase 15.1) — GREEN, read-only.

Both tools sandbox every path with AllowlistValidator.validate_sandbox_path()
(the same PATH semantics PolicyEngine enforces): traversal, escapes and
dangerous symlinks are rejected, allowed_paths are respected. Nothing is
written, nothing leaves the sandbox, files stream in chunks (never fully
loaded into memory).
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from security.allowlist import AllowlistValidator, SecurityValidationError

_HASH_CHUNK_BYTES = 65536
_MAX_SCAN_FILES = 20000
_MAX_DUPLICATE_GROUPS = 200
_MAX_WALK_ENTRIES = 50000


def _within_root(resolved: Path, root: Path) -> bool:
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def _iter_files(root: Path):
    """List (path, size) for regular files under root.

    - Never follows directory symlinks (followlinks=False).
    - Skips symlinked files resolving outside the sandbox.
    - Skips unreadable/vanishing files, counting them as skipped.
    Returns (files, skipped).
    """
    files: List[tuple] = []
    skipped = 0
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune symlinked directories defensively (followlinks=False already
        # avoids descending, but never list them as entries either).
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for filename in filenames:
            if seen >= _MAX_WALK_ENTRIES:
                skipped += 1
                continue
            seen += 1
            full = Path(dirpath) / filename
            try:
                if full.is_symlink():
                    target = full.resolve()
                    if not _within_root(target, root):
                        skipped += 1
                        continue
                if not full.is_file():
                    skipped += 1
                    continue
                files.append((full, full.stat().st_size))
            except OSError:
                skipped += 1
    return files, skipped


def _hash_file(path: Path) -> Optional[str]:
    """SHA-256 of a file in chunks; None when unreadable mid-scan."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


class FindDuplicatesArgs(BaseModel):
    directory: str = Field(..., description="Directory to scan for duplicate files")


class FindDuplicatesTool(BaseTool):
    """Find duplicate files by size pre-grouping, then SHA-256 of content."""

    name: str = "find_duplicates"
    description: str = (
        "Find duplicate files under a directory (grouped by size, confirmed "
        "by SHA-256 hash). Read-only and sandbox-contained."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = FindDuplicatesArgs
    param_kinds: Dict[str, ParamKind] = {"directory": ParamKind.PATH}

    async def execute(self, **kwargs: Any) -> ToolResult:
        validator = AllowlistValidator()
        try:
            root = validator.validate_sandbox_path(kwargs.get("directory", ""))
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )
        if not root.is_dir():
            return ToolResult.fail(
                error=f"Not a directory: {kwargs.get('directory')}",
                security_level=self.security_level,
            )

        files, skipped = _iter_files(root)
        if len(files) > _MAX_SCAN_FILES:
            skipped += len(files) - _MAX_SCAN_FILES
            files = files[:_MAX_SCAN_FILES]

        by_size: Dict[int, List[Path]] = {}
        for path, size in files:
            by_size.setdefault(size, []).append(path)

        duplicates = []
        for size in sorted(by_size):
            candidates = by_size[size]
            if len(candidates) < 2:
                continue
            by_hash: Dict[str, List[str]] = {}
            for path in candidates:
                digest = _hash_file(path)
                if digest is None:
                    skipped += 1
                    continue
                by_hash.setdefault(digest, []).append(str(path))
            for digest in sorted(by_hash):
                group = sorted(by_hash[digest])
                if len(group) > 1:
                    duplicates.append({
                        "hash": digest,
                        "size_bytes": size,
                        "files": group,
                    })
                    if len(duplicates) >= _MAX_DUPLICATE_GROUPS:
                        break
            if len(duplicates) >= _MAX_DUPLICATE_GROUPS:
                break

        return ToolResult.ok(
            data={
                "directory": str(root),
                "files_scanned": len(files),
                "skipped": skipped,
                "duplicate_groups": len(duplicates),
                "duplicates": duplicates,
            },
            security_level=self.security_level,
        )


class DiskUsageAnalysisArgs(BaseModel):
    path: str = Field(default=".", description="Root path to analyze")
    max_depth: int = Field(default=5, description="Max directory depth (0-10)")
    max_entries: int = Field(default=200, description="Max walked entries (1-2000)")
    top_n: int = Field(default=10, description="Top files/dirs to report (1-50)")


class DiskUsageAnalysisTool(BaseTool):
    """Summarize disk usage: totals, top files and top directories (bounded)."""

    name: str = "disk_usage_analysis"
    description: str = (
        "Analyze disk usage under a path: totals plus top files and "
        "directories. Depth and output are bounded; read-only."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = DiskUsageAnalysisArgs
    param_kinds: Dict[str, ParamKind] = {"path": ParamKind.PATH}

    async def execute(self, **kwargs: Any) -> ToolResult:
        validator = AllowlistValidator()
        try:
            root = validator.validate_sandbox_path(kwargs.get("path", "."))
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )
        if not root.exists():
            return ToolResult.fail(
                error=f"Path does not exist: {kwargs.get('path')}",
                security_level=self.security_level,
            )
        try:
            max_depth = max(0, min(int(kwargs.get("max_depth", 5)), 10))
            max_entries = max(1, min(int(kwargs.get("max_entries", 200)), 2000))
            top_n = max(1, min(int(kwargs.get("top_n", 10)), 50))
        except (TypeError, ValueError):
            return ToolResult.fail(
                error="max_depth, max_entries and top_n must be integers.",
                security_level=self.security_level,
            )

        total_size = 0
        file_count = 0
        dir_count = 0
        skipped = 0
        walked = 0
        top_files: List[tuple] = []
        dir_sizes: Dict[str, int] = {}

        root_resolved = root.resolve()
        if root_resolved.is_file():
            try:
                size = root_resolved.stat().st_size
            except OSError as e:
                return ToolResult.fail(
                    error=f"Cannot read file: {e}",
                    security_level=self.security_level,
                )
            return ToolResult.ok(
                data={
                    "path": str(root_resolved),
                    "total_size_bytes": size,
                    "files": 1,
                    "directories": 0,
                    "skipped": 0,
                    "top_files": [{"path": str(root_resolved), "size_bytes": size}],
                    "top_directories": [],
                },
                security_level=self.security_level,
            )
        for dirpath, dirnames, filenames in os.walk(root_resolved, followlinks=False):
            try:
                depth = len(Path(dirpath).relative_to(root_resolved).parts)
            except ValueError:
                continue
            if depth > max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not os.path.islink(os.path.join(dirpath, d))]
            dir_count += 1
            current_dir_size = 0
            for filename in filenames:
                if walked >= max_entries:
                    skipped += 1
                    continue
                walked += 1
                full = Path(dirpath) / filename
                try:
                    if full.is_symlink():
                        target = full.resolve()
                        if not _within_root(target, root_resolved):
                            skipped += 1
                            continue
                    if not full.is_file():
                        skipped += 1
                        continue
                    size = full.stat().st_size
                except OSError:
                    skipped += 1
                    continue
                file_count += 1
                total_size += size
                current_dir_size += size
                top_files.append((size, str(full)))
            dir_sizes[str(Path(dirpath))] = dir_sizes.get(str(Path(dirpath)), 0) + current_dir_size

        top_files_sorted = [
            {"path": path, "size_bytes": size}
            for size, path in sorted(top_files, reverse=True)[:top_n]
        ]
        top_dirs_sorted = [
            {"path": path, "size_bytes": size}
            for path, size in sorted(dir_sizes.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        ]
        return ToolResult.ok(
            data={
                "path": str(root_resolved),
                "total_size_bytes": total_size,
                "files": file_count,
                "directories": dir_count,
                "skipped": skipped,
                "top_files": top_files_sorted,
                "top_directories": top_dirs_sorted,
            },
            security_level=self.security_level,
        )
