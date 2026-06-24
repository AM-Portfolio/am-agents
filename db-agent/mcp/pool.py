from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.registry import get_registry
from mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPPool:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    def _server_def(self, alias: str) -> dict[str, Any] | None:
        cfg = get_registry().servers_config()
        if alias == "toolbox":
            universal = cfg.get("universal") or {}
            if settings.TOOLBOX_URL:
                return {
                    "transport": "http",
                    "url": settings.TOOLBOX_URL,
                }
            return universal or None
        satellites = cfg.get("satellites") or {}
        return satellites.get(alias)

    async def get_client(self, alias: str) -> MCPClient:
        if alias in self._clients:
            return self._clients[alias]
        spec = self._server_def(alias)
        if not spec:
            raise RuntimeError(f"MCP server '{alias}' not configured")
        client = MCPClient(
            transport=str(spec.get("transport", "stdio")),
            command=spec.get("command"),
            args=list(spec.get("args") or []),
            url=spec.get("url"),
            env=dict(spec.get("env") or {}),
        )
        self._clients[alias] = client
        return client

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, Any]
    ) -> Any:
        client = await self.get_client(server)
        return await client.call_tool(tool, arguments)

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


_pool: MCPPool | None = None


def get_mcp_pool() -> MCPPool:
    global _pool
    if _pool is None:
        _pool = MCPPool()
    return _pool
