#!/usr/bin/env python3
"""Spike kagent-grafana-mcp via MCP streamable HTTP (PyPI mcp SDK)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Avoid shadowing by local am-agents/tool-agent/mcp package
_agent_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_agent_root))

from tools._shared.grafana_time import grafana_time_to_rfc3339  # noqa: E402

# PyPI mcp SDK (exclude agent root from path for SDK imports below)
sys.path = [p for p in sys.path if Path(p).resolve() != _agent_root]

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:18000/mcp"


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

            ds_result = await session.call_tool("list_datasources", {})
            datasources = _parse_tool_text(ds_result)
            print("list_datasources:", json.dumps(datasources, indent=2)[:1200])

            items = datasources
            if isinstance(datasources, dict) and "datasources" in datasources:
                items = datasources["datasources"]
            loki_uid = None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("type") == "loki":
                        loki_uid = item.get("uid")
                        break

            if not loki_uid:
                print("No Loki datasource UID found")
                return 1

            print(f"Loki datasource UID: {loki_uid}")
            logs_result = await session.call_tool(
                "query_loki_logs",
                {
                    "datasourceUid": loki_uid,
                    "logql": '{namespace="am-apps-preprod"}',
                    "startRfc3339": grafana_time_to_rfc3339("now-15m"),
                    "endRfc3339": grafana_time_to_rfc3339("now"),
                    "limit": 5,
                },
            )
            logs = _parse_tool_text(logs_result)
            print("query_loki_logs:", json.dumps(logs, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
