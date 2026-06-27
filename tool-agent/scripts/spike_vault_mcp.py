#!/usr/bin/env python3
"""Spike kagent-vault-mcp via MCP streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_agent_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_agent_root))

sys.path = [p for p in sys.path if Path(p).resolve() != _agent_root]

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:18080/mcp"
DEFAULT_MOUNT = "apps"
LIST_PATH = "data/preprod/infra"


def _parse_tool_text(result) -> object:
    if not result.content:
        return result
    first = result.content[0]
    text = getattr(first, "text", None) or str(first)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"Connecting to {url}")

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"Discovered {len(tools.tools)} MCP tools")
            for tool in tools.tools[:12]:
                print(f"  - {tool.name}")

            mounts = await session.call_tool("list_mounts", {})
            print("list_mounts:", json.dumps(_parse_tool_text(mounts), indent=2)[:800])

            listed = await session.call_tool(
                "list_secrets",
                {"mount": DEFAULT_MOUNT, "path": LIST_PATH},
            )
            print("list_secrets:", json.dumps(_parse_tool_text(listed), indent=2)[:1200])

            read_result = await session.call_tool(
                "read_secret",
                {"mount": DEFAULT_MOUNT, "path": f"{LIST_PATH}/postgres"},
            )
            print("read_secret (postgres):", json.dumps(_parse_tool_text(read_result), indent=2)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
