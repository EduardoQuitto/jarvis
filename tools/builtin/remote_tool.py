"""Controlled remote-execution tool (CORE -> SERVER bridge).

Exposes a single Core tool, `remote_server_tool`, that proxies execution of
SHARED tools on the remote JARVIS SERVER node via RemoteNodeClient.

Safety rules (no exceptions):
- The LLM can only choose `tool_name` + `parameters`. It can NEVER choose
  URLs, hosts, shells, or Python code — the SERVER URL comes exclusively
  from JARVIS_SERVER_URL settings.
- Before executing, the SERVER tool list is consulted and only tools the
  SERVER advertises as SHARED are allowed. LOCAL_ONLY is always rejected
  locally, and the Core can never force its execution.
- Final authorization always happens on the SERVER (POST /tools/execute +
  ToolRegistry/PolicyEngine with confirmed=False). This tool never
  duplicates PolicyEngine logic and never executes anything locally.
"""

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field

from core.config import get_settings
from core.contracts.enums import ParamKind, SecurityLevel, ToolVisibility
from core.contracts.tool import BaseTool, ToolResult
from core.logger import get_logger
from core.network.node_client import RemoteNodeClient, RemoteNodeError

logger = get_logger("jarvis.tools.remote_server_tool")


class RemoteServerToolArgs(BaseModel):
    tool_name: str = Field(..., description="Name of the SHARED tool on the remote SERVER")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters forwarded to the remote SHARED tool",
    )


def _coerce_security_level(value: Any) -> SecurityLevel:
    try:
        return SecurityLevel(value)
    except (ValueError, TypeError):
        return SecurityLevel.GREEN


class RemoteServerTool(BaseTool):
    """Proxy tool that executes SHARED tools on the remote SERVER node."""

    name: str = "remote_server_tool"
    description: str = (
        "Execute a SHARED tool on the remote JARVIS SERVER node. "
        "Only tools advertised by the SERVER as SHARED are allowed; "
        "LOCAL_ONLY tools are always rejected."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    visibility: ToolVisibility = ToolVisibility.LOCAL_ONLY
    args_schema: Optional[Type[BaseModel]] = RemoteServerToolArgs
    # Only SERVER-advertised SHARED tool names are accepted (checked again
    # remotely); parameters travel opaquely to the SERVER PolicyEngine.
    param_kinds: Dict[str, ParamKind] = {"tool_name": ParamKind.IDENT}

    def __init__(self, client: Optional[RemoteNodeClient] = None):
        # Optional injected client (used by tests). Otherwise built from settings.
        self._client = client

    def _get_client(self) -> RemoteNodeClient:
        if self._client is not None:
            return self._client
        settings = get_settings()
        return RemoteNodeClient(
            base_url=settings.server_url,
            api_key=settings.server_api_key,
            timeout=settings.server_timeout,
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()
        if not settings.server_url:
            return ToolResult.fail(
                error="Remote SERVER is not configured (JARVIS_SERVER_URL is empty).",
                security_level=self.security_level,
            )

        tool_name = kwargs.get("tool_name", "")
        parameters = kwargs.get("parameters", {})
        if not isinstance(tool_name, str) or not tool_name.isidentifier():
            return ToolResult.fail(
                error=f"Invalid remote tool name: {tool_name!r}.",
                security_level=self.security_level,
            )
        if not isinstance(parameters, dict):
            return ToolResult.fail(
                error="Invalid parameters: 'parameters' must be an object.",
                security_level=self.security_level,
            )

        client = self._get_client()
        try:
            server_tools = await client.list_tools()
        except RemoteNodeError as e:
            logger.error("Remote SERVER list_tools failed (%s): %s", e.kind, e.message)
            return ToolResult.fail(
                error=f"Remote SERVER unavailable ({e.kind}): {e.message}",
                security_level=self.security_level,
            )
        except Exception as e:  # pragma: no cover - defensive, never leak raw
            logger.error("Remote SERVER list_tools unexpected error: %s", str(e))
            return ToolResult.fail(
                error="Remote SERVER unavailable (unknown error).",
                security_level=self.security_level,
            )

        match = next((t for t in server_tools if isinstance(t, dict) and t.get("name") == tool_name), None)
        if match is None:
            return ToolResult.fail(
                error=f"Tool '{tool_name}' is not available as SHARED on the remote SERVER.",
                security_level=self.security_level,
            )
        if match.get("visibility") != ToolVisibility.SHARED.value:
            return ToolResult.fail(
                error=(
                    f"Tool '{tool_name}' is blocked: visibility "
                    f"'{match.get('visibility')}' is not SHARED. "
                    "LOCAL_ONLY tools can never be executed remotely."
                ),
                security_level=self.security_level,
            )

        try:
            result = await client.execute_shared_tool(tool_name, parameters)
        except RemoteNodeError as e:
            logger.error("Remote SERVER execute failed (%s): %s", e.kind, e.message)
            return ToolResult.fail(
                error=f"Remote SERVER execution failed ({e.kind}): {e.message}",
                security_level=self.security_level,
            )
        except Exception as e:  # pragma: no cover - defensive, never leak raw
            logger.error("Remote SERVER execute unexpected error: %s", str(e))
            return ToolResult.fail(
                error="Remote SERVER execution failed (unknown error).",
                security_level=self.security_level,
            )

        remote_level = _coerce_security_level(result.get("security_level"))
        execution_time_ms = float(result.get("execution_time_ms") or 0.0)
        if result.get("success") is True:
            return ToolResult.ok(
                data=result.get("data"),
                security_level=remote_level,
                execution_time_ms=execution_time_ms,
            )
        return ToolResult.fail(
            error=str(result.get("error") or "Remote SERVER tool execution failed."),
            security_level=remote_level,
            execution_time_ms=execution_time_ms,
        )


def is_remote_server_configured() -> bool:
    """Whether JARVIS_SERVER_URL is set (remote bridge enabled)."""
    return bool(get_settings().server_url)


def register_remote_tool(registry) -> bool:
    """Register remote_server_tool when a SERVER URL is configured.

    Returns True when registered, False when skipped (server_url empty).
    Safe to call repeatedly — registry.register() overwrites by name.
    """
    if not is_remote_server_configured():
        return False
    registry.register(RemoteServerTool())
    return True
