"""Unit tests for am_mcp_client blocklist, cache, and auth gates."""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.clients.am_mcp_client import AmMcpClient, _mcp_tool_to_openai, _sse_url
from shared.context.request_context import auth_token_var


class TestHelpers:
    def test_sse_url_appends_sse(self):
        assert _sse_url("http://mcp:8080") == "http://mcp:8080/sse"

    def test_sse_url_keeps_existing_sse(self):
        assert _sse_url("http://mcp:8080/sse") == "http://mcp:8080/sse"

    def test_mcp_tool_to_openai(self):
        tool = MagicMock()
        tool.name = "get_portfolio_summary"
        tool.description = "summary"
        tool.inputSchema = {"type": "object", "properties": {"userId": {"type": "string"}}}
        out = _mcp_tool_to_openai(tool)
        assert out["type"] == "function"
        assert out["function"]["name"] == "get_portfolio_summary"
        assert "userId" in out["function"]["parameters"]["properties"]


class TestBlocklist:
    @pytest.mark.asyncio
    async def test_ask_finance_agent_blocked(self):
        client = AmMcpClient()
        result = await client.call_tool("ask_finance_agent", {})
        assert result["error"] == "TOOL_BLOCKED"

    @pytest.mark.asyncio
    async def test_call_tool_requires_token(self):
        client = AmMcpClient()
        token = auth_token_var.set("")
        try:
            result = await client.call_tool("get_portfolio_summary", {})
            assert result["error"] == "AUTH_REQUIRED"
        finally:
            auth_token_var.reset(token)


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_filters_blocklist_and_caches(self):
        client = AmMcpClient()
        allowed = MagicMock(name="allowed")
        allowed.name = "get_portfolio_summary"
        allowed.description = "ok"
        allowed.inputSchema = {"type": "object", "properties": {}}
        blocked = MagicMock(name="blocked")
        blocked.name = "ask_finance_agent"
        blocked.description = "no"
        blocked.inputSchema = {"type": "object", "properties": {}}

        listed = MagicMock()
        listed.tools = [allowed, blocked]

        session = AsyncMock()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock(return_value=listed)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        sse_cm = AsyncMock()
        sse_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        sse_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("mcp.client.sse.sse_client", return_value=sse_cm), patch(
            "mcp.ClientSession", return_value=session
        ):
            tools = await client.list_tools_openai(bearer_token="tok")
            assert len(tools) == 1
            assert tools[0]["function"]["name"] == "get_portfolio_summary"
            # Second call hits cache (no new session init required to succeed)
            tools2 = await client.list_tools_openai(bearer_token="tok")
            assert tools2 == tools
            session.list_tools.assert_awaited_once()
