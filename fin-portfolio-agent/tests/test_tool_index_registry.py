"""Regression: tool_index must read the same TOOL_REGISTRY as the agent."""
from shared.tools.registry import TOOL_REGISTRY, register_tool
from shared.tools.tool_index import retrieve_tools


@register_tool(description="Portfolio summary for tests")
def get_portfolio_summary(userId: str = "") -> str:
    return "{}"


def test_retrieve_tools_uses_shared_registry_when_chromadb_unavailable():
    """Without ChromaDB, retrieve_tools must not return an empty list."""
    tools = retrieve_tools("portfolio summary", top_k=10)
    assert len(tools) >= 1
    names = {t["function"]["name"] for t in tools}
    assert "get_portfolio_summary" in names
