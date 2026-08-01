"""
Intent Formatter — Deterministic tool-call → widgetId mapping.
No second LLM call. Reads which tools were actually executed
and maps them to the correct Flutter widget using a priority table.
"""
from typing import Dict, List, Optional, Tuple
from shared.schemas.intent import WidgetId


# Priority table: (tool_name_substring, widgetId, default_widget_params)
# First match wins. More specific tools should be listed first.
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
    ("get_portfolio_summary",    WidgetId.PORTFOLIO_SUMMARY, {}),
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
    Returns (widgetId, widgetParams) based on which tools were actually called.

    Args:
        tools_called: list of tool function names that ran during the agent turn.
        user_id:      injected into widgetParams so Flutter can use it for data fetching.
        tool_data:    mapping of tool_name → parsed tool return value (dict).
                      When present, the matched tool's data is embedded under the
                      "data" key in widgetParams so Flutter widgets receive the full
                      payload without making a second REST call.
    """
    resolved_tool_data = tool_data or {}

    for tool_name, widget_id, default_params in _INTENT_PRIORITY:
        if any(tool_name in called for called in tools_called):
            params: dict = {**default_params, "userId": user_id}
            if tool_name in resolved_tool_data:
                params["data"] = resolved_tool_data[tool_name]
            return widget_id, params

    # Nothing matched
    return WidgetId.TEXT_RESPONSE, {}
