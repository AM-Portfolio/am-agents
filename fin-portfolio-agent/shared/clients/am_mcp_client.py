"""MCP client for am-mcp-server — dynamic list_tools + call_tool."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from shared.context.request_context import auth_token_var, user_id_var
from shared.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_BLOCKLIST = frozenset({"ask_finance_agent"})


def _sse_url(base: str) -> str:
    root = base.rstrip("/")
    if root.endswith("/sse"):
        return root
    return f"{root}/sse"


def _parse_tool_result(result: Any) -> Any:
    content = getattr(result, "content", None)
    if not content:
        return result
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _mcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    name = getattr(tool, "name", None) or ""
    description = getattr(tool, "description", None) or name
    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema,
        },
    }


class AmMcpClient:
    """SSE client; tool catalog is discovered from the server (TTL cache)."""

    def __init__(self) -> None:
        self._cache_tools: list[dict[str, Any]] | None = None
        self._cache_at: float = 0.0

    @property
    def base_url(self) -> str:
        return settings.AM_MCP_SERVER_URL.rstrip("/")

    @property
    def blocklist(self) -> frozenset[str]:
        raw = settings.MCP_TOOL_BLOCKLIST
        names = {p.strip() for p in raw.split(",") if p.strip()}
        return frozenset(names) | _DEFAULT_BLOCKLIST

    def _cache_valid(self) -> bool:
        if self._cache_tools is None:
            return False
        return (time.monotonic() - self._cache_at) < settings.MCP_TOOL_CACHE_TTL_SECONDS

    async def list_tools_openai(self, *, bearer_token: str | None = None) -> list[dict[str, Any]]:
        if self._cache_valid() and self._cache_tools is not None:
            return list(self._cache_tools)

        token = bearer_token if bearer_token is not None else auth_token_var.get()
        if not token:
            logger.warning("list_tools skipped: no Bearer token")
            return []

        url = _sse_url(self.base_url)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            async with sse_client(
                url,
                headers=headers,
                timeout=settings.MCP_CLIENT_TIMEOUT_SECONDS,
                sse_read_timeout=settings.MCP_SSE_READ_TIMEOUT_SECONDS,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    tools_raw = getattr(listed, "tools", None) or []
                    openai_tools: list[dict[str, Any]] = []
                    for t in tools_raw:
                        name = getattr(t, "name", "") or ""
                        if not name or name in self.blocklist:
                            continue
                        openai_tools.append(_mcp_tool_to_openai(t))
                    self._cache_tools = openai_tools
                    self._cache_at = time.monotonic()
                    return list(openai_tools)
        except Exception as exc:
            logger.error("am-mcp-server list_tools failed: %s", exc)
            return []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        bearer_token: str | None = None,
    ) -> Any:
        if name in self.blocklist:
            return {
                "error": "TOOL_BLOCKED",
                "detail": f"MCP tool '{name}' is not allowed from fin-agent.",
            }

        token = bearer_token if bearer_token is not None else auth_token_var.get()
        if not token:
            return {
                "error": "AUTH_REQUIRED",
                "detail": "A Bearer access token is required to call am-mcp-server.",
            }

        args = dict(arguments or {})
        user_id = user_id_var.get()
        if user_id and user_id != "anonymous" and "userId" not in args:
            args.setdefault("userId", user_id)

        url = _sse_url(self.base_url)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            async with sse_client(
                url,
                headers=headers,
                timeout=settings.MCP_CLIENT_TIMEOUT_SECONDS,
                sse_read_timeout=settings.MCP_SSE_READ_TIMEOUT_SECONDS,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, args)
                    return _parse_tool_result(result)
        except Exception as exc:
            logger.error("am-mcp-server call_tool(%s) failed: %s", name, exc)
            return {
                "error": "MCP_UNAVAILABLE",
                "detail": f"am-mcp-server unreachable at {url}: {exc}",
            }


am_mcp_client = AmMcpClient()
