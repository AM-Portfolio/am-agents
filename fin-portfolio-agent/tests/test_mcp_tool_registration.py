"""MCP tool registration overrides local HTTP tools when MCP is configured."""
from shared.mcp_ext.tools import register_mcp_tools
from shared.tools.registry import TOOL_REGISTRY, _TOOL_IMPL, register_tool


def test_register_mcp_tools_overrides_existing():
    @register_tool(description="local", parameters={"type": "object", "properties": {}})
    def get_portfolio_summary(**kwargs):
        return "local"

    before = len(TOOL_REGISTRY)
    added = register_mcp_tools(override=True)
    assert added >= 1
    assert len(TOOL_REGISTRY) >= before
    assert "get_portfolio_summary" in _TOOL_IMPL
    # After override, impl should be async MCP wrapper, not the sync local function
    impl = _TOOL_IMPL["get_portfolio_summary"]
    assert impl.__name__ == "get_portfolio_summary"
    assert impl is not get_portfolio_summary
