"""
shared/mcp/tools.py - Registers MCP read tools into TOOL_REGISTRY.
Read tools always registered. Mutate tools only when AI_WRITE_TOOLS_ENABLED=true.
"""
from __future__ import annotations
import logging
from shared.mcp_ext.client import mcp_client
from shared.core.config import settings

logger = logging.getLogger(__name__)

# Agent registry name → live MCP tool name (catalog drift).
_MCP_NAME_ALIASES = {
    "get_holdings_list": "get_holdings",
}

# MCP tool execution often runs off the SSE request thread, so UserContext is empty
# and AM_DEFAULT_USER=user1 wins. Send JWT sub as userId; MCP prefers JWT when present.
_BIND_USERID_TOOLS = frozenset({
    "get_portfolio_summary",
    "get_holdings",
    "get_holdings_list",
    "get_holding_detail",
    "get_sector_allocation",
    "get_top_movers",
    "get_market_cap_allocation",
    "get_recent_activity",
    "get_trade_history",
})

# MCP names (after alias) that require user JWT — shared with McpClient.
USER_SCOPED_MCP_READ_TOOLS = frozenset(
    name for name in _BIND_USERID_TOOLS if name != "get_holdings_list"
)

# Names that exist on am-mcp-server @Tool catalog (read). Used by alignment tests.
MCP_CATALOG_READ_TOOLS = frozenset({
    "get_portfolio_summary",
    "get_holdings",
    "get_holding_detail",
    "get_market_movers",
    "get_stock_quote",
    "get_indices_data",
    "search_instruments",
    "get_recent_activity",
    "get_trade_history",
    "get_sector_allocation",
    "get_top_movers",
    "get_market_cap_allocation",
})

# Phantom names removed from agent registry until MCP implements them (Wave 2).
PHANTOM_AGENT_TOOLS = frozenset({
    "get_basket_list",
    "get_basket_details",
    "get_benchmark_comparison",
    "get_fund_details",
    "analyze_etf_overlap",
    "count_etfs",
    "get_risk_metrics",
    "get_performance_chart",
})


def bound_mcp_user_id() -> str:
    from shared.context.jwt_context import bearer_token, jwt_subject
    from shared.context.request_context import auth_token_var, user_id_var

    token = bearer_token(auth_token_var.get() or "")
    uid = jwt_subject(token) if token else None
    if uid:
        return uid
    ctx = (user_id_var.get() or "").strip()
    if ctx and ctx not in {"anonymous", "-"}:
        return ctx
    return ""


def bind_mcp_tool_args(name: str, mcp_name: str, args: dict) -> dict:
    out = dict(args)
    if name in _BIND_USERID_TOOLS or mcp_name in _BIND_USERID_TOOLS:
        uid = bound_mcp_user_id()
        if uid:
            out["userId"] = uid
        else:
            out.pop("userId", None)
    return out


def _mcp_tool(name: str):
    async def _impl(**kwargs) -> str:
        mcp_name = _MCP_NAME_ALIASES.get(name, name)
        args = bind_mcp_tool_args(name, mcp_name, kwargs)
        return await mcp_client.call_tool(mcp_name, args)

    _impl.__name__ = name
    return _impl


_READ_TOOLS = [
    (
        "get_portfolio_summary",
        "[portfolio] Summary of the user's portfolio: total value, P&L, day change. [read]",
        {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]},
    ),
    (
        "get_holdings_list",
        "[portfolio] List all holdings with quantities and values. [read]",
        {
            "type": "object",
            "properties": {"userId": {"type": "string"}, "portfolioId": {"type": "string"}},
            "required": ["userId"],
        },
    ),
    (
        "get_holding_detail",
        "[portfolio] Detailed info for one holding by symbol. [read]",
        {
            "type": "object",
            "properties": {"userId": {"type": "string"}, "symbol": {"type": "string"}},
            "required": ["userId", "symbol"],
        },
    ),
    (
        "get_market_movers",
        "[market] Market-wide / index top gainers and losers (Nifty, Sensex). NOT the user's portfolio. [read]",
        {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "GAINERS or LOSERS"},
                "limit": {"type": "integer", "default": 10},
                "indexSymbol": {"type": "string", "description": "e.g. NIFTY 50"},
            },
            "required": [],
        },
    ),
    (
        "get_stock_quote",
        "[market] Live quote (LTP) for an NSE symbol e.g. RELIANCE, TCS. [read]",
        {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    ),
    (
        "get_indices_data",
        "[market] Latest index levels (NIFTY, SENSEX, BANKNIFTY). [read]",
        {
            "type": "object",
            "properties": {"symbols": {"type": "string", "description": "Comma-separated, optional"}},
            "required": [],
        },
    ),
    (
        "search_instruments",
        "[market] Search stocks/ETFs by company name or partial symbol. [read]",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    (
        "get_recent_activity",
        "[trade] Recent buys/sells and transactions, newest first. [read]",
        {
            "type": "object",
            "properties": {"userId": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
            "required": ["userId"],
        },
    ),
    (
        "get_trade_history",
        "[trade] Full transaction history for a specific stock symbol. [read]",
        {
            "type": "object",
            "properties": {"userId": {"type": "string"}, "symbol": {"type": "string"}},
            "required": ["userId", "symbol"],
        },
    ),
    (
        "get_sector_allocation",
        "[analysis] Sector breakdown of THIS user's portfolio (IT, Banking, etc.). NOT market sectors. [read]",
        {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]},
    ),
    (
        "get_top_movers",
        "[analysis] Top gainers/losers in THIS user's portfolio by P&L. NOT Nifty/market movers. [read]",
        {
            "type": "object",
            "properties": {"userId": {"type": "string"}, "timeFrame": {"type": "string"}},
            "required": ["userId"],
        },
    ),
    (
        "get_market_cap_allocation",
        "[analysis] Large/mid/small cap breakdown of the user's portfolio. [read]",
        {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]},
    ),
]

_MUTATE_TOOLS = [
    ("place_order", "Place a buy or sell order. [mutate]", {"type":"object","properties":{"userId":{"type":"string"},"symbol":{"type":"string"},"qty":{"type":"number"},"side":{"type":"string","enum":["buy","sell"]}},"required":["userId","symbol","qty","side"]}),
    ("modify_order", "Modify an existing order. [mutate]", {"type":"object","properties":{"orderId":{"type":"string"},"qty":{"type":"number"}},"required":["orderId"]}),
    ("cancel_order", "Cancel a pending order. [mutate]", {"type":"object","properties":{"orderId":{"type":"string"}},"required":["orderId"]}),
    ("create_basket", "Create a new investment basket. [mutate]", {"type":"object","properties":{"userId":{"type":"string"},"name":{"type":"string"}},"required":["userId","name"]}),
    ("add_basket_item", "Add a stock to a basket. [mutate]", {"type":"object","properties":{"basketId":{"type":"string"},"symbol":{"type":"string"},"weight":{"type":"number"}},"required":["basketId","symbol","weight"]}),
    ("remove_basket_item", "Remove a stock from a basket. [mutate]", {"type":"object","properties":{"basketId":{"type":"string"},"symbol":{"type":"string"}},"required":["basketId","symbol"]}),
    ("rebalance_basket", "Rebalance basket weights to target allocation. [mutate]", {"type":"object","properties":{"basketId":{"type":"string"}},"required":["basketId"]}),
]

# Local HTTP tools that must not reach the LLM when MCP is the call path.
LEGACY_DOMAIN_TOOLS = frozenset({
    "get_benchmark_comparison",
    "get_holding_details",
    "analyze_etf_overlap",
    "count_etfs",
    "get_fund_details",
    "web_search",
}) | PHANTOM_AGENT_TOOLS

# Meta-tools for API testing (kept when ENABLE_API_TESTING).
_API_TESTING_TOOL_NAMES = frozenset({
    "register_api_spec",
    "search_apis",
    "get_api_workflow",
    "generate_payload",
    "execute_api",
    "validate_response",
})


def mcp_agent_tool_allowlist() -> frozenset[str]:
    """Agent-facing tool names that map to MCP (plus optional mutate tools)."""
    names = {name for name, _, _ in _READ_TOOLS}
    if settings.AI_WRITE_TOOLS_ENABLED:
        names |= {name for name, _, _ in _MUTATE_TOOLS}
    return frozenset(names)


def prune_legacy_domain_tools() -> int:
    """
    Drop legacy analysis_client HTTP tools from TOOL_REGISTRY when MCP is configured.

    register_mcp_tools(override=True) replaces overlapping names, but phantom / ETF /
    benchmark tools remain and inflate the LLM catalog (~18 tools).
    """
    if not (settings.MCP_BASE_URL or "").strip():
        return 0

    from shared.tools.registry import OPENAPI_EXECUTOR_MAP, TOOL_REGISTRY, _TOOL_IMPL

    allow = mcp_agent_tool_allowlist()
    kept: list[dict] = []
    removed = 0

    for tool in TOOL_REGISTRY:
        name = tool.get("function", {}).get("name")
        if not name:
            kept.append(tool)
            continue

        if name in allow:
            kept.append(tool)
            continue
        if settings.ENABLE_API_TESTING and name in _API_TESTING_TOOL_NAMES:
            kept.append(tool)
            continue
        if name in OPENAPI_EXECUTOR_MAP:
            kept.append(tool)
            continue
        if name in LEGACY_DOMAIN_TOOLS:
            _TOOL_IMPL.pop(name, None)
            removed += 1
            continue

        kept.append(tool)

    TOOL_REGISTRY[:] = kept
    if removed:
        logger.info(
            "prune_legacy_domain_tools: removed %d tools (registry=%d allow=%d mcp=%s)",
            removed,
            len(TOOL_REGISTRY),
            len(allow),
            settings.MCP_BASE_URL,
        )
    return removed


def register_mcp_tools(*, override: bool = False) -> int:
    from shared.tools.registry import TOOL_REGISTRY, _TOOL_IMPL
    count = 0
    all_tools = _READ_TOOLS + (_MUTATE_TOOLS if settings.AI_WRITE_TOOLS_ENABLED else [])

    def _remove_tool(tool_name: str) -> None:
        TOOL_REGISTRY[:] = [
            t for t in TOOL_REGISTRY
            if t.get("function", {}).get("name") != tool_name
        ]
        _TOOL_IMPL.pop(tool_name, None)

    for name, desc, params in all_tools:
        exists = any(t.get("function", {}).get("name") == name for t in TOOL_REGISTRY)
        if exists and not override:
            continue
        if exists and override:
            _remove_tool(name)
        TOOL_REGISTRY.append({"type": "function", "function": {"name": name, "description": desc, "parameters": params}})
        _TOOL_IMPL[name] = _mcp_tool(name)
        count += 1
    prune_legacy_domain_tools()
    logger.info(
        "register_mcp_tools: %d tools (override=%s write_enabled=%s mcp_base=%s registry=%d)",
        count,
        override,
        settings.AI_WRITE_TOOLS_ENABLED,
        settings.MCP_BASE_URL,
        len(TOOL_REGISTRY),
    )
    return count
