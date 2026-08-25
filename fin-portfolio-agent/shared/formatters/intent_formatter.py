"""
Intent Formatter — Deterministic tool-call -> widgetId mapping.
No second LLM call. Maps which tools actually ran to the correct Flutter widget.
"""
from typing import Dict, List, Optional, Tuple
from shared.schemas.intent import WidgetId

# Priority table: (tool_name_substring, widgetId, default_widget_params)
# First match wins.
_INTENT_PRIORITY: List[Tuple[str, str, dict]] = [
    ("get_top_movers",           WidgetId.TOP_MOVERS,        {"limit": 10}),
    ("analyze_etf_overlap",      WidgetId.ETF_ANALYSIS,      {}),
    ("count_etfs",               WidgetId.ETF_ANALYSIS,      {}),
    ("get_fund_details",         WidgetId.ETF_ANALYSIS,      {}),
    ("get_sector_allocation",    WidgetId.ALLOCATION_PIE,    {}),
    ("get_holdings_list",        WidgetId.HOLDINGS_TABLE,    {}),
    ("get_holding_details",      WidgetId.HOLDINGS_TABLE,    {}),
    ("get_recent_activity",      WidgetId.RECENT_ACTIVITY,   {"limit": 20}),
    ("get_trade_history",        WidgetId.RECENT_ACTIVITY,   {}),
    ("get_benchmark_comparison", WidgetId.BENCHMARK,         {}),
    ("get_risk_metrics",         WidgetId.RISK_METRICS,      {}),
    ("get_performance_chart",    WidgetId.PERFORMANCE_CHART, {}),
    # Basket tools
    ("get_basket_list",          WidgetId.BASKET_CARD,       {}),
    ("get_basket_details",       WidgetId.BASKET_CARD,       {}),
    ("create_basket",            WidgetId.BASKET_CARD,       {}),
    ("add_basket_item",          WidgetId.BASKET_CARD,       {}),
    ("remove_basket_item",       WidgetId.BASKET_CARD,       {}),
    ("rebalance_basket",         WidgetId.BASKET_CARD,       {}),
    # Portfolio summary (lower priority than specific tools)
    ("get_portfolio_summary",    WidgetId.PORTFOLIO_SUMMARY, {}),
    # API testing
    ("search_apis",              WidgetId.API_TEST_WIDGET,   {}),
    ("get_api_workflow",         WidgetId.API_TEST_WIDGET,   {}),
    ("generate_payload",         WidgetId.API_TEST_WIDGET,   {}),
    ("execute_api",              WidgetId.API_TEST_WIDGET,   {}),
    ("validate_response",        WidgetId.API_TEST_WIDGET,   {}),
    ("web_search",               WidgetId.TEXT_RESPONSE,     {}),
]


def resolve_intent(
    tools_called: List[str],
    user_id: str,
    tool_data: Optional[Dict[str, dict]] = None,
) -> Tuple[str, dict]:
    """
    Returns (widgetId, widgetParams) based on tools actually called.
    tool_data: tool_name -> parsed result dict, embedded as 'data' in widgetParams.
    """
    resolved = tool_data or {}
    for tool_name, widget_id, default_params in _INTENT_PRIORITY:
        if any(tool_name in called for called in tools_called):
            params: dict = {**default_params, "userId": user_id}
            if tool_name in resolved:
                params["data"] = resolved[tool_name]
            return widget_id, params
    return WidgetId.TEXT_RESPONSE, {}


def parse_agent_result(
    tools_called: List[str],
    user_id: str,
    tool_data: Optional[Dict[str, dict]] = None,
) -> dict:
    """Single function: tool outcomes -> {widgetId, widgetParams}."""
    widget_id, widget_params = resolve_intent(tools_called, user_id, tool_data)
    return {"widgetId": widget_id, "widgetParams": widget_params}
