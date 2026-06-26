#!/usr/bin/env python3
"""HTTP MCP server (STREAMABLE_HTTP) for kagent RemoteMCPServer -> tool-agent REST/SSE."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_agent_root = Path(__file__).resolve().parents[1]
sys.path = [p for p in sys.path if Path(p).resolve() != _agent_root]

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_tools  # noqa: E402

HOST = os.environ.get("TOOL_AGENT_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("TOOL_AGENT_MCP_PORT", "8085"))

mcp = FastMCP("AM Tool Agent", host=HOST, port=PORT)


@mcp.tool()
def tool_agent_health() -> str:
    """Check tool-agent health."""
    return mcp_tools.tool_agent_health()


@mcp.tool()
def tool_agent_ready() -> str:
    """Check tool-agent readiness."""
    return mcp_tools.tool_agent_ready()


@mcp.tool()
def tool_agent_list_backends() -> str:
    """List enabled backends."""
    return mcp_tools.tool_agent_list_backends()


@mcp.tool()
def tool_agent_plan(query: str, backend: str | None = None, read_only: bool = True) -> str:
    """Plan only — parse intent and resolve params without executing."""
    return mcp_tools.tool_agent_plan(query, backend=backend, read_only=read_only)


@mcp.tool()
def tool_agent_execute(intent_json: str, include_summary: bool = True, max_rows: int = 100) -> str:
    """Execute intent JSON from tool_agent_plan."""
    return mcp_tools.tool_agent_execute(intent_json, include_summary=include_summary, max_rows=max_rows)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
