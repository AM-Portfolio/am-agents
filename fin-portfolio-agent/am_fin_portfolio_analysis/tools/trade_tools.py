"""
Trade Domain Tools — using REST client (Phase H.5)
Data from am-analysis REST API (port 8060).
"""
import json
import logging
from shared.tools.registry import register_tool
from ..clients.analysis_client import analysis_client

logger = logging.getLogger(__name__)


def _format(data, label: str) -> str:
    if isinstance(data, dict) and "error" in data:
        return f"Error retrieving {label}: {data['error']}. Make sure am-analysis is running on port 8060."
    return f"{label}:\n{json.dumps(data, indent=2)}"


@register_tool(
    description="Get recent portfolio activity: buy/sell transactions and portfolio changes.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Number of recent items (default: 20)"}
        },
        "required": []
    }
)
def get_recent_activity(limit: int = 20) -> str:
    data = analysis_client.get_recent_activity(limit=limit)
    return _format(data, f"Recent Activity (last {limit})")


@register_tool(
    description="Get full trade/transaction history for a specific stock.",
    parameters={
        "type": "object",
        "properties": {
            "stock_name": {"type": "string", "description": "Stock symbol or name"}
        },
        "required": ["stock_name"]
    }
)
def get_trade_history(stock_name: str) -> str:
    data = analysis_client.get_recent_activity(limit=100)
    if isinstance(data, dict) and "error" in data:
        return _format(data, "Trade History")
    activities = data if isinstance(data, list) else data.get("activities", [])
    filtered = [a for a in activities
                if stock_name.lower() in str(a.get("symbol", "")).lower()]
    if not filtered:
        return f"No trade history found for '{stock_name}'."
    return f"Trade History for {stock_name}:\n{json.dumps(filtered, indent=2)}"
