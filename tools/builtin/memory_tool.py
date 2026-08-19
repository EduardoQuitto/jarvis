"""Memory search tool for querying JARVIS memory."""

from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from memory.sqlite_provider import SQLiteMemoryProvider


class SearchMemoryArgs(BaseModel):
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, description="Maximum results")


class SearchMemoryTool(BaseTool):
    """Search through JARVIS memory for relevant information."""

    name: str = "search_memory"
    description: str = "Search memory for stored information, past conversations, or learned facts."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = SearchMemoryArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 10)

        try:
            memory = SQLiteMemoryProvider()
            results = await memory.search_memory(query=query, limit=limit)
            return ToolResult.ok(
                data={"results": results, "count": len(results)},
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(
                error=f"Memory search failed: {e}",
                security_level=self.security_level,
            )
