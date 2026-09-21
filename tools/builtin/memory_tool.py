"""Memory search tool for querying JARVIS memory."""

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.config import get_settings
from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from core.logger import get_logger
from core.network.central_state_client import CentralStateError
from memory import get_memory_provider
from memory.sqlite_provider import SQLiteMemoryProvider

logger = get_logger("jarvis.tools.memory")


class SearchMemoryArgs(BaseModel):
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, description="Maximum results")


class SearchMemoryTool(BaseTool):
    """Search through JARVIS memory for relevant information."""

    name: str = "search_memory"
    description: str = "Search memory for stored information, past conversations, or learned facts."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = SearchMemoryArgs
    # The query is bound as a SQL parameter, never interpolated.
    param_kinds: Dict[str, ParamKind] = {"query": ParamKind.FREE_TEXT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 10)

        try:
            memory = get_memory_provider()
            results = await memory.search_memory(query=query, limit=limit)
            return ToolResult.ok(
                data={"results": results, "count": len(results)},
                security_level=self.security_level,
            )
        except CentralStateError as e:
            # Central mode with an unreachable SERVER: explicit failure when
            # required, local SQLite fallback otherwise (never a fake answer).
            if get_settings().central_state_required:
                return ToolResult.fail(
                    error=f"Central memory unavailable ({e.kind}): {e.message}",
                    security_level=self.security_level,
                )
            logger.warning(
                "Central memory failed (%s); falling back to local SQLite", e.kind,
            )
            try:
                results = await SQLiteMemoryProvider().search_memory(query=query, limit=limit)
                return ToolResult.ok(
                    data={"results": results, "count": len(results)},
                    security_level=self.security_level,
                )
            except Exception as fallback_error:
                return ToolResult.fail(
                    error=f"Memory search failed: {fallback_error}",
                    security_level=self.security_level,
                )
        except Exception as e:
            return ToolResult.fail(
                error=f"Memory search failed: {e}",
                security_level=self.security_level,
            )
