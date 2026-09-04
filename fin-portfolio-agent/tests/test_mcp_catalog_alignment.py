"""Agent read-tool registry must stay aligned with MCP_TOOL_CATALOG.md."""
from shared.mcp_ext.tools import (
    MCP_CATALOG_READ_TOOLS,
    PHANTOM_AGENT_TOOLS,
    _MCP_NAME_ALIASES,
    _READ_TOOLS,
    bind_mcp_tool_args,
    register_mcp_tools,
)
from shared.prompts.system import get_system_prompt, PROMPT_VERSION
from shared.formatters.intent_formatter import resolve_intent
from shared.schemas.intent import WidgetId


REQUIRED_READ_TOOLS = frozenset({
    "get_market_movers",
    "get_stock_quote",
    "get_indices_data",
    "get_recent_activity",
    "get_sector_allocation",
    "get_market_cap_allocation",
    "get_portfolio_summary",
    "get_holdings_list",
})


def _resolved_mcp_name(agent_name: str) -> str:
    return _MCP_NAME_ALIASES.get(agent_name, agent_name)


def test_read_tools_resolve_to_mcp_catalog():
    register_mcp_tools(override=True)
    for name, _, _ in _READ_TOOLS:
        mcp_name = _resolved_mcp_name(name)
        assert mcp_name in MCP_CATALOG_READ_TOOLS, f"{name} -> {mcp_name} not on MCP catalog"


def test_phantom_tools_not_registered():
    register_mcp_tools(override=True)
    registered = {name for name, _, _ in _READ_TOOLS}
    assert not registered & PHANTOM_AGENT_TOOLS


def test_required_tools_present():
    register_mcp_tools(override=True)
    registered = {name for name, _, _ in _READ_TOOLS}
    missing = REQUIRED_READ_TOOLS - registered
    assert not missing, f"Missing required tools: {missing}"


def test_bind_userid_for_trade_and_analysis():
    from shared.context.request_context import auth_token_var, user_id_var
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "jwt-trade-1"}).encode()).decode().rstrip("=")
    token = f"{header}.{payload}.sig"
    auth_token_var.set(f"Bearer {token}")
    user_id_var.set("ctx-user")
    try:
        for tool in ("get_recent_activity", "get_sector_allocation", "get_market_cap_allocation"):
            args = bind_mcp_tool_args(tool, tool, {"userId": "spoof"})
            assert args["userId"] == "jwt-trade-1", tool
    finally:
        auth_token_var.set("")
        user_id_var.set("anonymous")


def test_prompt_routes_market_vs_portfolio_movers():
    prompt = get_system_prompt(enable_portfolio=True)
    assert PROMPT_VERSION == "1.2.0"
    assert "get_market_movers" in prompt
    assert "get_top_movers" in prompt
    assert "get_recent_activity" in prompt
    assert "get_trade_history" in prompt
    assert "get_sector_allocation" in prompt
    assert "Portfolio" in prompt and "Market" in prompt and "Trade" in prompt and "Analysis" in prompt
    assert "get_fund_details" not in prompt
    assert "get_basket_list" not in prompt


def test_widget_intent_for_new_tools():
    wid, _ = resolve_intent(["get_market_movers"], "u1")
    assert wid == WidgetId.TOP_MOVERS
    wid2, _ = resolve_intent(["get_holdings"], "u1")
    assert wid2 == WidgetId.HOLDINGS_TABLE
