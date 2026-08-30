"""
shared/mcp/tools.py - Registers all 27 MCP tools into TOOL_REGISTRY.
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

# JWT-scoped portfolio tools: MCP schema is portfolioId-only (additionalProperties false).
# Identity comes from the forwarded Bearer JWT — do not send userId as an arg.
_STRIP_USERID_TOOLS = frozenset({
    "get_portfolio_summary",
    "get_holdings",
    "get_holdings_list",
    "get_holding_detail",
    "get_portfolio_overviews",
    "get_portfolio_by_id",
    "get_portfolio_advanced_analytics",
})


def _mcp_tool(name: str):
    async def _impl(**kwargs) -> str:
        mcp_name = _MCP_NAME_ALIASES.get(name, name)
        args = dict(kwargs)
        if name in _STRIP_USERID_TOOLS or mcp_name in _STRIP_USERID_TOOLS:
            args.pop("userId", None)
        return await mcp_client.call_tool(mcp_name, args)

    _impl.__name__ = name
    return _impl


_READ_TOOLS = [
    ("get_portfolio_summary", "Get a summary of the user's portfolio including total value, P&L, day change. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("get_holdings_list", "List all holdings in the user's portfolio with quantities and values. [read]", {"type":"object","properties":{"userId":{"type":"string"},"portfolioId":{"type":"string"}},"required":["userId"]}),
    ("get_holding_detail", "Get detailed info for a specific holding including price history. [read]", {"type":"object","properties":{"userId":{"type":"string"},"symbol":{"type":"string"}},"required":["userId","symbol"]}),
    ("get_sector_allocation", "Get portfolio sector allocation breakdown as percentages. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("get_benchmark_comparison", "Compare portfolio performance against a benchmark index. [read]", {"type":"object","properties":{"userId":{"type":"string"},"benchmark":{"type":"string"}},"required":["userId"]}),
    ("get_top_movers", "Get today's top gaining and losing stocks. [read]", {"type":"object","properties":{"limit":{"type":"integer","default":10}},"required":[]}),
    ("get_fund_details", "Get details about a mutual fund or ETF by symbol. [read]", {"type":"object","properties":{"symbol":{"type":"string"}},"required":["symbol"]}),
    ("get_basket_list", "List all investment baskets available to the user. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("get_basket_details", "Get contents and weights of a specific basket. [read]", {"type":"object","properties":{"basketId":{"type":"string"}},"required":["basketId"]}),
    ("get_trade_history", "Get the user's past trade history. [read]", {"type":"object","properties":{"userId":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["userId"]}),
    ("get_recent_activity", "Get the user's recent portfolio activity and transactions. [read]", {"type":"object","properties":{"userId":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["userId"]}),
    ("analyze_etf_overlap", "Analyze overlap between ETFs in the portfolio to spot concentration risk. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("count_etfs", "Count the number of ETFs in the portfolio. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("get_risk_metrics", "Get risk metrics for the portfolio: VaR, beta, Sharpe ratio. [read]", {"type":"object","properties":{"userId":{"type":"string"}},"required":["userId"]}),
    ("get_performance_chart", "Get performance chart data for the portfolio over a time period. [read]", {"type":"object","properties":{"userId":{"type":"string"},"period":{"type":"string","default":"1M"}},"required":["userId"]}),
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
    logger.info(
        "register_mcp_tools: %d tools (override=%s write_enabled=%s mcp_base=%s)",
        count,
        override,
        settings.AI_WRITE_TOOLS_ENABLED,
        settings.MCP_BASE_URL,
    )
    return count
