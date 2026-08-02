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
The main FastAPI app mounts authenticated SSE transport at /ai/mcp.
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
import am_fin_portfolio_analysis.tools.portfolio_tools   # noqa: F401
import am_fin_portfolio_analysis.tools.analysis_tools    # noqa: F401
import am_fin_portfolio_analysis.tools.trade_tools       # noqa: F401


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
    from shared.context.request_context import auth_token_var, user_id_var
    from shared.middleware.auth_middleware import (
        AUTH_JWKS_URL,
        subject_from_claims,
        verify_jwt_claims,
    )
    from mcp.server.sse import SseServerTransport
    from starlette.responses import JSONResponse

    server = Server("am-fin-agent")
    if not hasattr(server, "list_tools"):
        raise AttributeError(
            "mcp Server has no list_tools (SDK mismatch); disable local /ai/mcp"
        )

    # ── list_tools: expose a single smart meta-tool ──────────────────────────
    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
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
        args.pop("userId", None)
        args.pop("user_id", None)
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
        result_str = await execute_tool(op_id, args)

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

    _sse_transport = SseServerTransport("/messages")

    def _bearer_from_scope(scope: dict) -> str | None:
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"authorization":
                value = raw_value.decode("latin-1")
                if value.lower().startswith("bearer "):
                    return value.split(" ", 1)[1].strip()
        return None

    class AuthenticatedMcpSseApp:
        """ASGI SSE transport that establishes verified per-session auth context."""

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await JSONResponse({"detail": "HTTP transport required"}, status_code=400)(
                    scope, receive, send
                )
                return

            token = _bearer_from_scope(scope)
            if not token:
                await JSONResponse({"detail": "Bearer token required"}, status_code=401)(
                    scope, receive, send
                )
                return
            if not AUTH_JWKS_URL:
                await JSONResponse(
                    {"detail": "AUTH_JWKS_URL is required for MCP"},
                    status_code=503,
                )(scope, receive, send)
                return
            claims = verify_jwt_claims(token)
            subject = subject_from_claims(claims or {})
            if not subject:
                await JSONResponse({"detail": "Invalid Bearer token"}, status_code=401)(
                    scope, receive, send
                )
                return

            path = scope.get("path", "").rstrip("/") or "/"
            if scope["method"] == "POST" and path == "/messages":
                await _sse_transport.handle_post_message(scope, receive, send)
                return
            if scope["method"] != "GET" or path != "/":
                await JSONResponse({"detail": "Not found"}, status_code=404)(
                    scope, receive, send
                )
                return

            auth_context = auth_token_var.set(token)
            user_context = user_id_var.set(subject)
            try:
                async with _sse_transport.connect_sse(scope, receive, send) as streams:
                    await server.run(
                        streams[0],
                        streams[1],
                        InitializationOptions(
                            server_name="am-fin-agent",
                            server_version="1.0.0",
                            capabilities=types.ServerCapabilities(
                                tools=types.ToolsCapability(listChanged=True)
                            ),
                        ),
                    )
            finally:
                auth_token_var.reset(auth_context)
                user_id_var.reset(user_context)

    mcp_sse_app = AuthenticatedMcpSseApp()


# ─── Entry points ─────────────────────────────────────────────────────────────

async def run_stdio():
    """Run the MCP server over stdio (for Claude Desktop)."""
    if not _MCP_AVAILABLE:
        logger.error("mcp package not installed. Run: pip install mcp")
        sys.exit(1)

    from mcp.server.stdio import stdio_server

    token = os.getenv("ASRAX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("ASRAX_ACCESS_TOKEN is required for MCP stdio transport")
    if not AUTH_JWKS_URL:
        raise RuntimeError("AUTH_JWKS_URL is required for MCP stdio transport")
    claims = verify_jwt_claims(token)
    subject = subject_from_claims(claims or {})
    if not subject:
        raise RuntimeError("ASRAX_ACCESS_TOKEN is invalid")

    logger.info("Starting MCP server (stdio transport)...")
    auth_context = auth_token_var.set(token)
    user_context = user_id_var.set(subject)
    try:
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
    finally:
        auth_token_var.reset(auth_context)
        user_id_var.reset(user_context)


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
