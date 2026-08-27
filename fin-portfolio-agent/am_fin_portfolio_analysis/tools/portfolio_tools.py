"""
Portfolio Domain Tools — using REST client (Phase H.5)
All data now comes from am-analysis REST API (port 8060).

NOTE: All functions accept **kwargs to absorb extra args (e.g. userId)
that the LLM passes based on the MCP tool schema.
"""
import json
import logging
from shared.tools.registry import register_tool
from ..clients.analysis_client import analysis_client

logger = logging.getLogger(__name__)


def _format(data: dict, label: str) -> str:
    if "error" in data:
        return f"Error retrieving {label}: {data['error']}. Make sure am-analysis is running on port 8060."
    return json.dumps(data)


@register_tool(
    description="Get overall portfolio performance: total invested, current value, P&L, and all holdings.",
    parameters={"type": "object", "properties": {}, "required": []}
)
def get_portfolio_summary(**kwargs) -> str:
    data = analysis_client.get_dashboard_summary()
    return _format(data, "Portfolio Summary")


@register_tool(
    description="Get the complete list of all stock and ETF holdings in the user's portfolio.",
    parameters={"type": "object", "properties": {}, "required": []}
)
def get_holdings_list(**kwargs) -> str:
    data = analysis_client.get_holdings()
    return _format(data, "Holdings")


@register_tool(
    description="Get detailed P&L and performance metrics for a specific stock in the user's portfolio.",
    parameters={
        "type": "object",
        "properties": {
            "stock_name": {"type": "string", "description": "Stock name or symbol (e.g., 'HDFC', 'Reliance')"}
        },
        "required": ["stock_name"]
    }
)
def get_holding_details(stock_name: str = "", **kwargs) -> str:
    data = analysis_client.get_holdings()
    if "error" in data:
        return _format(data, "Holdings")
    holdings = data if isinstance(data, list) else data.get("holdings", [])
    match = next(
        (h for h in holdings if stock_name.lower() in str(h.get("symbol", "")).lower()),
        None
    )
    if match:
        return f"Details for {stock_name}:\n{json.dumps(match, indent=2)}"
    return f"Stock '{stock_name}' not found in your portfolio."


@register_tool(
    description="Get the user's portfolio comparison against the NIFTY 50 benchmark.",
    parameters={"type": "object", "properties": {}, "required": []}
)
def get_benchmark_comparison(**kwargs) -> str:
    data = analysis_client.get_dashboard_summary()
    return _format(data, "Portfolio vs Benchmark")
