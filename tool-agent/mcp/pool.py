from __future__ import annotations


class McpPool:
    async def call_tool(self, server: str, tool_name: str, params: dict) -> object:
        raise RuntimeError(f"MCP pool not configured (server={server}, tool={tool_name})")


_pool: McpPool | None = None


def get_mcp_pool() -> McpPool:
    global _pool
    if _pool is None:
        _pool = McpPool()
    return _pool
