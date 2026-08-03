"""Map MCP tool names to stable artifact types (not Flutter widget ids)."""
from __future__ import annotations

from typing import Any

# MCP tool name -> artifactType. Unknown tools fall back to data.generic.v1.
TOOL_ARTIFACT_TYPES: dict[str, str] = {
    "get_portfolio_summary": "portfolio.summary.v1",
    "get_holdings": "holdings.list.v1",
    "get_holding_detail": "holdings.detail.v1",
    "get_portfolio_overviews": "portfolio.overviews.v1",
    "get_portfolio_by_id": "portfolio.detail.v1",
    "get_portfolio_advanced_analytics": "portfolio.analytics.v1",
    "get_top_movers": "portfolio.movers.v1",
    "get_sector_allocation": "portfolio.sector_allocation.v1",
    "get_market_cap_allocation": "portfolio.market_cap.v1",
    "get_recent_activity": "trades.recent.v1",
    "get_trade_history": "trades.history.v1",
    "get_unrealised_pnl": "trades.unrealised_pnl.v1",
    "filter_trades": "trades.filter.v1",
    "get_trades_by_date_range": "trades.date_range.v1",
    "get_trade_metrics": "trades.metrics.v1",
    "get_trade_portfolio_summaries": "trades.portfolio_summary.v1",
    "get_stock_quote": "market.quote.v1",
    "search_instruments": "market.search.v1",
    "get_historical_data": "market.history.v1",
    "get_market_movers": "market.movers.v1",
    "get_sector_performance": "market.sector.v1",
    "get_indices_data": "market.indices.v1",
    "get_basket_opportunities": "basket.opportunities.v1",
    "get_basket_exposure": "basket.exposure.v1",
    "get_basket_allocations": "basket.allocations.v1",
    "get_basket_preview": "basket.preview.v1",
    "calculate_basket_quantities": "basket.quantities.v1",
}


def resolve_artifact(
    tools_called: list[str],
    tool_data: dict[str, Any] | None = None,
) -> tuple[str, Any]:
    """
    Pick primary artifactType + data payload from tools executed this turn.
    Priority: last matching tool in tools_called that has a known artifact type.
    """
    data_map = tool_data or {}
    if not tools_called:
        return "text.v1", None

    for name in reversed(tools_called):
        payload = data_map.get(name)
        if isinstance(payload, dict) and (payload.get("error") or payload.get("ok") is False):
            return "error.v1", payload
        artifact = TOOL_ARTIFACT_TYPES.get(name)
        if artifact:
            return artifact, payload if name in data_map else None

    last = tools_called[-1]
    payload = data_map.get(last)
    if isinstance(payload, dict) and (payload.get("error") or payload.get("ok") is False):
        return "error.v1", payload
    return "data.generic.v1", payload
