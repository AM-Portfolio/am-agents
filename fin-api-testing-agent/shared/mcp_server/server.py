"""
mcp_server/server.py
=============
MCP (Model Context Protocol) server for am-fin-agent.

Exposes all registered tools (hand-written + auto-generated from OpenAPI specs)
to any MCP-compatible client: Claude Desktop, Cursor, Continue, etc.

Smart-scale strategy
--------------------
With potentially 100-600 tools, listing every one in list_tools() would overflow
the MCP client's context. Instead, this server exposes a SINGLE meta-tool
`call_api` that internally uses the ChromaDB vector index (tool_index.py) to
find and execute the best matching tool.

Running the MCP server (stdio transport - works with Claude Desktop)
--------------------------------------------------------------------
    python -m mcp_server.server           # or:
    python /path/to/mcp_server/server.py

Claude Desktop config (~/.config/claude/claude_desktop_config.json)
--------------------------------------------------------------------
    {
      "mcpServers": {
        "am-fin-agent": {
          "command": "python",
          "args": ["/path/to/am-fin-agent/mcp_server/server.py"]
        }
      }
    }

SSE transport (for browser-based MCP clients)
---------------------------------------------
Set the env var MCP_TRANSPORT=sse and start as a regular FastAPI app alongside
the main api.py.  The SSE endpoint will be available at /mcp/sse.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


# ─── Ensure the project root is on the path ──────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ─── Bootstrap: trigger @register_tool decorators ────────────────────────────
import shared.tools.portfolio_tools   # noqa: F401
import shared.tools.analysis_tools    # noqa: F401
import shared.tools.trade_tools       # noqa: F401
import shared.tools.meta_tools        # noqa: F401


# ─── MCP Server ───────────────────────────────────────────────────────────────

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    import mcp.types as types
    _MCP_AVAILABLE = True
except ImportError as e:
    import traceback
    _MCP_AVAILABLE = False
    logger.error(f"MCP import failed: {e}")
    logger.error(traceback.format_exc())
    logger.error(
        "mcp package not found. Install with: pip install mcp\n"
        "MCP server will not be available."
    )

if _MCP_AVAILABLE:
    from shared.tools.registry import TOOL_REGISTRY, execute_tool
    from shared.tools.tool_index import retrieve_tools, tool_count

    server = Server("am-fin-agent")

    # ── list_tools: expose a single smart meta-tool ──────────────────────────
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """
        Smart-scale mode: expose one `call_api` meta-tool.
        Internally uses ChromaDB to route to the right endpoint.

        This keeps the MCP client context small regardless of how many
        micro-service endpoints are registered.
        """
        return [
            types.Tool(
                name="call_api",
                description=(
                    "Find and execute any backend API based on a natural-language description. "
                    "The server will automatically locate the best matching endpoint from all "
                    "registered micro-services and execute it.\n\n"
                    f"Currently {tool_count() or len(TOOL_REGISTRY)} tools available across "
                    "all micro-services."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Natural language description of what you want to do, "
                                "e.g. 'get portfolio summary for user u-42' or "
                                "'fetch current price of RELIANCE'."
                            ),
                        },
                        "args": {
                            "type": "object",
                            "description": (
                                "Optional key-value arguments for the API call. "
                                "Leave empty if none are needed."
                            ),
                            "additionalProperties": True,
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "How many candidate tools to consider (default 3).",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # Also expose a tool_search tool so clients can explore what's available
            types.Tool(
                name="search_tools",
                description="Search available tools by keyword. Returns matching tool names and descriptions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword to search for"},
                        "top_k": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
        ]

    # ── call_tool: resolve + execute ─────────────────────────────────────────
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name == "call_api":
            return await _handle_call_api(arguments)
        elif name == "search_tools":
            return await _handle_search_tools(arguments)
        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _handle_call_api(arguments: dict) -> list[types.TextContent]:
        query = arguments.get("query", "")
        args = arguments.get("args", {}) or {}
        top_k = int(arguments.get("top_k", 3))

        if not query:
            return [types.TextContent(type="text", text="Error: 'query' parameter is required.")]

        # Semantic search → find best matching tool(s)
        candidates = retrieve_tools(query, top_k=top_k)

        if not candidates:
            return [types.TextContent(type="text", text="No matching API found for your query.")]

        # Pick the top result
        top_tool = candidates[0]
        op_id = top_tool.get("function", {}).get("name", "")
        description = top_tool.get("function", {}).get("description", "")

        logger.info("MCP call_api: query=%r → selected tool=%s", query, op_id)

        # Execute
        result_str = execute_tool(op_id, args)

        try:
            result = json.loads(result_str)
            formatted = json.dumps(result, indent=2)
        except (ValueError, TypeError):
            formatted = result_str

        response = (
            f"**Tool selected:** `{op_id}`\n"
            f"**Description:** {description}\n\n"
            f"**Result:**\n```json\n{formatted}\n```"
        )
        return [types.TextContent(type="text", text=response)]

    async def _handle_search_tools(arguments: dict) -> list[types.TextContent]:
        query = arguments.get("query", "")
        top_k = int(arguments.get("top_k", 10))

        candidates = retrieve_tools(query, top_k=top_k)
        lines = []
        for t in candidates:
            fn = t.get("function", {})
            lines.append(f"- **{fn.get('name')}**: {fn.get('description', '')}")

        text = f"Found {len(candidates)} tools matching '{query}':\n\n" + "\n".join(lines)
        return [types.TextContent(type="text", text=text)]


# ─── Entry points ─────────────────────────────────────────────────────────────

async def run_stdio():
    """Run the MCP server over stdio (for Claude Desktop)."""
    if not _MCP_AVAILABLE:
        logger.error("mcp package not installed. Run: pip install mcp")
        sys.exit(1)

    from mcp.server.stdio import stdio_server

    logger.info("Starting MCP server (stdio transport)...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="am-fin-agent",
                server_version="1.0.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability(listChanged=True)
                ),
            ),
        )


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
