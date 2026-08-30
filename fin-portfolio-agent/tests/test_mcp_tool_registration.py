"""MCP tool registration overrides local HTTP tools when MCP is configured."""
from shared.mcp_ext.tools import _MCP_NAME_ALIASES, _STRIP_USERID_TOOLS, register_mcp_tools
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
    assert "get_holdings_list" in _STRIP_USERID_TOOLS
    assert "get_portfolio_summary" in _STRIP_USERID_TOOLS
