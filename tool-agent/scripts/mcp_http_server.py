#!/usr/bin/env python3
"""HTTP MCP server (STREAMABLE_HTTP) for kagent RemoteMCPServer -> tool-agent REST/SSE."""

from __future__ import annotations

import json
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
def kafka_list_topics(max_rows: int = 100) -> str:
    """List all Kafka topics in preprod (read-only). Call this for ANY user question about kafka topics."""
    return mcp_tools.kafka_list_topics(max_rows=max_rows)


@mcp.tool()
def mongodb_list_databases(max_rows: int = 100) -> str:
    """List MongoDB databases in preprod (read-only). Call for mongo database listing questions."""
    return mcp_tools.mongodb_list_databases(max_rows=max_rows)


@mcp.tool()
def tool_agent_infra_query(backend: str, query: str = "") -> str:
    """Read-only infra query. backend: kafka|mongodb|postgres|redis|vault|qdrant|grafana. query: short NL e.g. list topics."""
    q = query.strip() or f"list {backend}"
    return mcp_tools.tool_agent_query_slim(q, backend=backend)


@mcp.tool()
def tool_agent_health() -> str:
    """Check tool-agent health."""
    return mcp_tools.tool_agent_health()


@mcp.tool()
def tool_agent_list_backends() -> str:
    """List enabled infra backends."""
    return mcp_tools.tool_agent_list_backends()


@mcp.tool()
def tool_agent_plan(query: str, backend: str | None = None, read_only: bool = True) -> str:
    """Plan only — parse intent without executing."""
    return mcp_tools.tool_agent_plan(query, backend=backend, read_only=read_only)


@mcp.tool()
def tool_agent_execute(intent_json: str, include_summary: bool = True, max_rows: int = 100) -> str:
    """Execute intent JSON from tool_agent_plan."""
    return mcp_tools.tool_agent_execute(intent_json, include_summary=include_summary, max_rows=max_rows)


@mcp.tool()
def tool_agent_query(query: str, backend: str | None = None, read_only: bool = True, max_rows: int = 100) -> str:
    """One-shot read-only NL query. Prefer kafka_list_topics for kafka topic lists."""
    return mcp_tools.tool_agent_query_slim(
        query, backend=backend, read_only=read_only, max_rows=max_rows
    )


@mcp.tool()
def tool_agent_plan_and_execute(
    query: str, backend: str | None = None, read_only: bool = True, max_rows: int = 100
) -> str:
    """Plan then execute in one call."""
    return mcp_tools.tool_agent_plan_and_execute(
        query, backend=backend, read_only=read_only, max_rows=max_rows
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
