"""B1: legacy HTTP domain tools pruned when MCP is configured."""
import pytest

from shared.core.config import settings
from shared.mcp_ext.tools import (
    LEGACY_DOMAIN_TOOLS,
    mcp_agent_tool_allowlist,
    prune_legacy_domain_tools,
    register_mcp_tools,
)
from shared.tools.registry import TOOL_REGISTRY, _TOOL_IMPL, register_tool


@pytest.fixture(autouse=True)
def _restore_tool_registry():
    saved_registry = list(TOOL_REGISTRY)
    saved_impl = dict(_TOOL_IMPL)
    yield
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.extend(saved_registry)
    _TOOL_IMPL.clear()
    _TOOL_IMPL.update(saved_impl)


def test_prune_removes_legacy_domain_tools(monkeypatch):
    monkeypatch.setattr(settings, "MCP_BASE_URL", "http://am-mcp-server:8080", raising=False)
    TOOL_REGISTRY.clear()
    _TOOL_IMPL.clear()

    @register_tool(description="legacy benchmark", parameters={"type": "object", "properties": {}})
    def get_benchmark_comparison(**kwargs):
        return "legacy"

    @register_tool(description="local", parameters={"type": "object", "properties": {}})
    def get_top_movers(**kwargs):
        return "local"

    register_mcp_tools(override=True)
    names = {t.get("function", {}).get("name") for t in TOOL_REGISTRY}

    assert "get_top_movers" in names
    assert "get_benchmark_comparison" not in names
    assert "get_benchmark_comparison" not in _TOOL_IMPL
    assert len(names) == len(mcp_agent_tool_allowlist())


def test_prune_noop_without_mcp_base_url(monkeypatch):
    monkeypatch.setattr(settings, "MCP_BASE_URL", "", raising=False)
    TOOL_REGISTRY.clear()
    _TOOL_IMPL.clear()

    @register_tool(description="legacy", parameters={"type": "object", "properties": {}})
    def web_search(**kwargs):
        return "legacy"

    removed = prune_legacy_domain_tools()
    assert removed == 0
    assert "web_search" in _TOOL_IMPL


def test_legacy_domain_tools_includes_phantoms():
    assert "get_basket_list" in LEGACY_DOMAIN_TOOLS
    assert "web_search" in LEGACY_DOMAIN_TOOLS
