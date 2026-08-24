"""File operations tool for reading/writing files on the server."""

from pathlib import Path
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from security.allowlist import AllowlistValidator, SecurityValidationError


class ReadFileArgs(BaseModel):
    file_path: str = Field(..., description="Path to the file to read")


class WriteFileArgs(BaseModel):
    file_path: str = Field(..., description="Path to write the file")
    content: str = Field(..., description="Content to write")


class ListDirArgs(BaseModel):
    directory: str = Field(default=".", description="Directory path to list")


class ReadFileTool(BaseTool):
    """Read the contents of a file."""

    name: str = "read_file"
    description: str = "Read the contents of a file from the filesystem."
    security_level: SecurityLevel = SecurityLevel.YELLOW
    args_schema: Optional[Type[BaseModel]] = ReadFileArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        validator = AllowlistValidator()

        try:
            resolved = validator.validate_file_path(file_path, must_exist=False)
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )

        try:
            content = resolved.read_text(encoding="utf-8")
            return ToolResult.ok(
                data={"content": content, "path": str(resolved)},
                security_level=self.security_level,
            )
        except FileNotFoundError:
            return ToolResult.fail(error=f"File not found: {file_path}", security_level=self.security_level)
        except Exception as e:
            return ToolResult.fail(error=f"Error reading file: {e}", security_level=self.security_level)


class WriteFileTool(BaseTool):
    """Write content to a file."""

    name: str = "write_file"
    description: str = "Write content to a file on the filesystem."
    security_level: SecurityLevel = SecurityLevel.YELLOW
    args_schema: Optional[Type[BaseModel]] = WriteFileArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")
        validator = AllowlistValidator()

        try:
            resolved = validator.validate_file_path(file_path, must_exist=False)
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult.ok(
                data={"bytes_written": len(content.encode("utf-8")), "path": str(resolved)},
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(error=f"Error writing file: {e}", security_level=self.security_level)


class ListDirTool(BaseTool):
    """List contents of a directory."""

    name: str = "list_dir"
    description: str = "List files and subdirectories in a directory."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = ListDirArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        directory = kwargs.get("directory", ".")
        validator = AllowlistValidator()

        try:
            resolved = validator.validate_file_path(directory, must_exist=False)
        except SecurityValidationError as e:
            return ToolResult.fail(
                error=f"Access denied: {e}",
                security_level=self.security_level,
            )

        try:
            entries = []
            for entry in sorted(resolved.iterdir()):
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else None,
                })
            return ToolResult.ok(
                data={"entries": entries, "path": str(resolved)},
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(error=f"Error listing directory: {e}", security_level=self.security_level)
