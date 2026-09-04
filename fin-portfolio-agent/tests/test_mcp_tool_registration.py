"""MCP tool registration overrides local HTTP tools when MCP is configured."""
from shared.context.request_context import auth_token_var, user_id_var
from shared.mcp_ext.tools import (
    _BIND_USERID_TOOLS,
    _MCP_NAME_ALIASES,
    bind_mcp_tool_args,
    register_mcp_tools,
)
from shared.tools.registry import TOOL_REGISTRY, _TOOL_IMPL, register_tool


def test_register_mcp_tools_overrides_existing():
    @register_tool(description="local", parameters={"type": "object", "properties": {}})
    def get_top_movers(**kwargs):
        return "local"

    before = len(TOOL_REGISTRY)
    added = register_mcp_tools(override=True)
    assert added >= 1
    assert len(TOOL_REGISTRY) >= before
    assert "get_top_movers" in _TOOL_IMPL
    impl = _TOOL_IMPL["get_top_movers"]
    assert impl.__name__ == "get_top_movers"
    assert impl is not get_top_movers


def test_mcp_overrides_portfolio_summary():
    @register_tool(description="local", parameters={"type": "object", "properties": {}})
    def get_portfolio_summary(**kwargs):
        return "local"

    register_mcp_tools(override=True)
    impl = _TOOL_IMPL["get_portfolio_summary"]
    assert impl is not get_portfolio_summary
    assert impl.__name__ == "get_portfolio_summary"


def test_holdings_list_aliases_to_get_holdings():
    assert _MCP_NAME_ALIASES["get_holdings_list"] == "get_holdings"
    assert "get_holdings_list" in _BIND_USERID_TOOLS
    assert "get_portfolio_summary" in _BIND_USERID_TOOLS


def test_bind_mcp_args_overwrites_llm_userid_with_jwt():
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "jwt-user-1"}).encode()).decode().rstrip("=")
    token = f"{header}.{payload}.sig"
    auth_token_var.set(f"Bearer {token}")
    user_id_var.set("context-user")
    try:
        args = bind_mcp_tool_args(
            "get_portfolio_summary",
            "get_portfolio_summary",
            {"userId": "llm-spoof"},
        )
        assert args["userId"] == "jwt-user-1"
    finally:
        auth_token_var.set("")
        user_id_var.set("anonymous")


def test_bind_mcp_args_uses_context_when_no_jwt():
    auth_token_var.set("")
    user_id_var.set("670116d7-8683-4f35-bdb6-7cf6fb122068")
    try:
        args = bind_mcp_tool_args("get_holdings_list", "get_holdings", {})
        assert args["userId"] == "670116d7-8683-4f35-bdb6-7cf6fb122068"
        sector = bind_mcp_tool_args("get_sector_allocation", "get_sector_allocation", {})
        assert sector["userId"] == "670116d7-8683-4f35-bdb6-7cf6fb122068"
    finally:
        user_id_var.set("anonymous")
