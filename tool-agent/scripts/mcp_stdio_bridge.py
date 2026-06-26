#!/usr/bin/env python3
"""Stdio MCP bridge: any IDE mcp.json -> tool-agent HTTP API."""

from __future__ import annotations

import sys
from pathlib import Path

_agent_root = Path(__file__).resolve().parents[1]
sys.path = [p for p in sys.path if Path(p).resolve() != _agent_root]

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_tools  # noqa: E402

mcp = FastMCP("AM Tool Agent")


@mcp.tool()
def tool_agent_health() -> str:
    """Check tool-agent health (enabled tools, env)."""
    return mcp_tools.tool_agent_health()


@mcp.tool()
def tool_agent_ready() -> str:
    """Check tool-agent readiness (registry, LLM, Langfuse, catalog cache)."""
    return mcp_tools.tool_agent_ready()


@mcp.tool()
def tool_agent_list_backends() -> str:
    """List enabled tool-agent backends (mongodb, postgres, kafka, vault, ...)."""
    return mcp_tools.tool_agent_list_backends()


@mcp.tool()
def tool_agent_plan(query: str, backend: str | None = None, read_only: bool = True) -> str:
    """Parse NL query into intent only (no execution). Always pass backend for agent callers."""
    return mcp_tools.tool_agent_plan(query, backend=backend, read_only=read_only)


@mcp.tool()
def tool_agent_query(
    query: str,
    backend: str | None = None,
    read_only: bool = True,
    include_summary: bool = True,
    max_rows: int = 100,
) -> str:
    """Run NL query end-to-end. Prefer tool_agent_plan + tool_agent_execute for staged visibility."""
    return mcp_tools.tool_agent_query(
        query,
        backend=backend,
        read_only=read_only,
        include_summary=include_summary,
        max_rows=max_rows,
    )


@mcp.tool()
def tool_agent_execute(intent_json: str, include_summary: bool = False, max_rows: int = 100) -> str:
    """Execute structured intent JSON from tool_agent_plan."""
    return mcp_tools.tool_agent_execute(intent_json, include_summary=include_summary, max_rows=max_rows)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
