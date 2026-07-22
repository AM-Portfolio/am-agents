from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.mcp_client import RemoteMcpClient


class McpCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def mcp_client() -> RemoteMcpClient:
    return RemoteMcpClient(
        settings.octoperf_mcp_url,
        timeout_seconds=settings.mcp_timeout_seconds,
        bearer_token=settings.octoperf_mcp_token,
    )


async def list_mcp_tools() -> list[dict[str, Any]]:
    client = mcp_client()
    return await client.list_tools()


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> Any:
    client = mcp_client()
    return await client.call_tool(name, arguments)


async def mcp_ping() -> dict[str, Any]:
    tools = await list_mcp_tools()
    return {
        "mcp_url": settings.octoperf_mcp_url,
        "tool_count": len(tools),
        "tools": [t["name"] for t in tools],
        "has_token": bool(settings.octoperf_mcp_token),
        "status": "ok",
    }
