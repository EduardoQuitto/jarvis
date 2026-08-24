"""Internet tools — web search and URL fetching."""

import json
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel, ToolVisibility
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
    visibility: ToolVisibility = ToolVisibility.SHARED
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
    """Fetch content from a URL with SSRF protection."""

    name: str = "fetch_url"
    description: str = "Fetch the content of a web page or API endpoint."
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.SHARED
    args_schema: Optional[Type[BaseModel]] = FetchUrlArgs

    MAX_REDIRECTS = 5
    MAX_RESPONSE_BYTES = 512_000  # 512KB

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = kwargs.get("timeout", 30)

        try:
            from security.net_guard import validate_url, validate_redirect_url, SSRFBlocked
        except ImportError:
            return ToolResult.fail(
                error="net_guard module not available",
                security_level=self.security_level,
            )

        try:
            validate_url(url)
        except (SSRFBlocked, ValueError) as e:
            return ToolResult.fail(
                error=f"URL blocked by security policy: {e}",
                security_level=self.security_level,
            )

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=float(timeout),
                follow_redirects=False,
            ) as client:
                current_url = url
                for hop in range(self.MAX_REDIRECTS + 1):
                    response = await client.get(
                        current_url,
                        headers={"User-Agent": "JARVIS/0.1"},
                    )

                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if not location:
                            break
                        # Resolve relative redirects
                        if location.startswith("/"):
                            from urllib.parse import urlparse as _urlparse
                            base = _urlparse(current_url)
                            location = f"{base.scheme}://{base.netloc}{location}"
                        try:
                            validate_redirect_url(location, current_url)
                        except (SSRFBlocked, ValueError) as e:
                            return ToolResult.fail(
                                error=f"Redirect blocked by security policy: {e}",
                                security_level=self.security_level,
                            )
                        current_url = location
                        continue

                    break

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
                text = response.text[:50000]
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
