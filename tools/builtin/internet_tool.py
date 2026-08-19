"""Internet tools — web search and URL fetching."""

import json
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query")
    num_results: int = Field(default=5, description="Number of results to return")


class FetchUrlArgs(BaseModel):
    url: str = Field(..., description="URL to fetch")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class WebSearchTool(BaseTool):
    """Search the web for information."""

    name: str = "web_search"
    description: str = "Search the web for current information on any topic."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = WebSearchArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        num_results = kwargs.get("num_results", 5)

        try:
            import httpx

            # Use DuckDuckGo Lite as a simple search backend
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://lite.duckduckgo.com/lite",
                    params={"q": query},
                    headers={"User-Agent": "JARVIS/0.1"},
                )

                if response.status_code == 200:
                    # Parse simple results (DuckDuckGo Lite returns HTML)
                    text = response.text
                    # Extract titles and URLs from the simple HTML
                    results = []
                    lines = text.split("\n")
                    for line in lines:
                        if "href=" in line and "http" in line:
                            # Simple extraction - get first URL
                            start = line.find("href=") + 6
                            end = line.find('"', start)
                            if end > start:
                                url = line[start:end]
                                if url.startswith("http"):
                                    results.append({"url": url, "title": url})
                                    if len(results) >= num_results:
                                        break

                    return ToolResult.ok(
                        data={"results": results, "query": query},
                        security_level=self.security_level,
                    )
                else:
                    return ToolResult.fail(
                        error=f"Search failed with status {response.status_code}",
                        security_level=self.security_level,
                    )

        except ImportError:
            return ToolResult.fail(
                error="httpx not available. Install with: pip install httpx",
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(
                error=f"Web search failed: {e}",
                security_level=self.security_level,
            )


class FetchUrlTool(BaseTool):
    """Fetch content from a URL."""

    name: str = "fetch_url"
    description: str = "Fetch the content of a web page or API endpoint."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = FetchUrlArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = kwargs.get("timeout", 30)

        try:
            import httpx

            async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "JARVIS/0.1"},
                )

                content_type = response.headers.get("content-type", "")

                if "json" in content_type:
                    try:
                        data = response.json()
                        return ToolResult.ok(
                            data={"content": data, "format": "json", "status": response.status_code},
                            security_level=self.security_level,
                        )
                    except json.JSONDecodeError:
                        pass

                # Return text content (truncated for safety)
                text = response.text[:50000]  # Limit to 50KB
                return ToolResult.ok(
                    data={"content": text, "format": "text", "status": response.status_code},
                    security_level=self.security_level,
                )

        except ImportError:
            return ToolResult.fail(
                error="httpx not available. Install with: pip install httpx",
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(
                error=f"URL fetch failed: {e}",
                security_level=self.security_level,
            )
