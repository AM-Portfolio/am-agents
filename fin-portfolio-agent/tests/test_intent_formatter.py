"""
Tests for formatters/intent_formatter.py — resolve_intent().

Covers:
- Empty tools_called → TEXT_RESPONSE widgetId, empty params
- Single tool match → userId injected, no "data" key without tool_data
- tool_data provided with matching tool → params["data"] equals the dict
- tool_data with non-matching tool → no "data" key
- tool_data=None → no crash, no "data" key
- tool_data={} → no crash, no "data" key
- Priority ordering: first match in _INTENT_PRIORITY wins
- Backward-compatible 2-arg call (omit tool_data)
"""
import sys
import os

# Allow importing project modules without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.formatters.intent_formatter import resolve_intent, _INTENT_PRIORITY
from shared.schemas.intent import WidgetId


# ─── helpers ─────────────────────────────────────────────────────────────────

def _priority_tool(index: int) -> str:
    """Return the tool_name substring at a given position in _INTENT_PRIORITY."""
    return _INTENT_PRIORITY[index][0]


def _priority_widget(index: int) -> str:
    """Return the widgetId at a given position in _INTENT_PRIORITY."""
    return _INTENT_PRIORITY[index][1]


# ─── tests ───────────────────────────────────────────────────────────────────

class TestResolveIntentNoTools:
    def test_empty_tools_returns_text_response(self):
        widget_id, params = resolve_intent([], "u1")
        assert widget_id == WidgetId.TEXT_RESPONSE

    def test_empty_tools_returns_empty_params(self):
        _widget_id, params = resolve_intent([], "u1")
        assert params == {}

    def test_empty_tools_no_user_id_in_params(self):
        """When nothing matches, widgetParams is {} — userId is NOT injected."""
        _widget_id, params = resolve_intent([], "u1")
        assert "userId" not in params


class TestResolveIntentSingleTool:
    def test_portfolio_summary_returns_correct_widget(self):
        widget_id, _params = resolve_intent(["get_portfolio_summary"], "u42")
        assert widget_id == WidgetId.PORTFOLIO_SUMMARY

    def test_portfolio_summary_injects_user_id(self):
        _widget_id, params = resolve_intent(["get_portfolio_summary"], "u42")
        assert params["userId"] == "u42"

    def test_portfolio_summary_no_data_key_without_tool_data(self):
        _widget_id, params = resolve_intent(["get_portfolio_summary"], "u42")
        assert "data" not in params

    def test_holdings_list_returns_holdings_table(self):
        widget_id, _params = resolve_intent(["get_holdings_list"], "user1")
        assert widget_id == WidgetId.HOLDINGS_TABLE

    def test_top_movers_returns_top_movers_widget(self):
        widget_id, params = resolve_intent(["get_top_movers"], "user1")
        assert widget_id == WidgetId.TOP_MOVERS
        # default_params for get_top_movers includes limit=10
        assert params.get("limit") == 10

    def test_web_search_returns_text_response(self):
        widget_id, _params = resolve_intent(["web_search"], "user1")
        assert widget_id == WidgetId.TEXT_RESPONSE


class TestResolveIntentWithToolData:
    def test_matching_tool_data_appears_in_params(self):
        payload = {"totalValue": 1_500_000, "totalHoldings": 15}
        _widget_id, params = resolve_intent(
            ["get_portfolio_summary"],
            "u42",
            tool_data={"get_portfolio_summary": payload},
        )
        assert params["data"]["totalValue"] == 1_500_000
        assert params["data"]["totalHoldings"] == 15

    def test_data_key_exact_value(self):
        payload = {"k": "v"}
        _widget_id, params = resolve_intent(
            ["get_portfolio_summary"],
            "u1",
            tool_data={"get_portfolio_summary": payload},
        )
        assert params["data"] is payload

    def test_non_matching_tool_data_produces_no_data_key(self):
        """tool_data has a different tool name — "data" must not appear in params."""
        _widget_id, params = resolve_intent(
            ["get_portfolio_summary"],
            "u1",
            tool_data={"get_top_movers": {"items": []}},
        )
        assert "data" not in params

    def test_tool_data_none_no_crash(self):
        widget_id, params = resolve_intent(
            ["get_portfolio_summary"], "u1", tool_data=None
        )
        assert widget_id == WidgetId.PORTFOLIO_SUMMARY
        assert "data" not in params

    def test_tool_data_empty_dict_no_crash(self):
        widget_id, params = resolve_intent(
            ["get_portfolio_summary"], "u1", tool_data={}
        )
        assert widget_id == WidgetId.PORTFOLIO_SUMMARY
        assert "data" not in params

    def test_user_id_still_injected_with_tool_data(self):
        payload = {"x": 1}
        _widget_id, params = resolve_intent(
            ["get_portfolio_summary"],
            "alice",
            tool_data={"get_portfolio_summary": payload},
        )
        assert params["userId"] == "alice"
        assert params["data"] == payload


class TestResolveIntentPriorityOrdering:
    def test_first_priority_tool_wins_over_later_one(self):
        """
        _INTENT_PRIORITY[0] is get_top_movers → TOP_MOVERS.
        _INTENT_PRIORITY[10] is get_portfolio_summary → PORTFOLIO_SUMMARY.
        When both are present the first entry in the table must win.
        """
        first_tool = _priority_tool(0)    # get_top_movers
        later_tool = _priority_tool(10)   # get_portfolio_summary
        first_widget = _priority_widget(0)

        widget_id, _params = resolve_intent([first_tool, later_tool], "u1")
        assert widget_id == first_widget

    def test_second_priority_tool_wins_when_first_absent(self):
        second_tool = _priority_tool(1)   # analyze_etf_overlap
        second_widget = _priority_widget(1)

        widget_id, _params = resolve_intent([second_tool], "u1")
        assert widget_id == second_widget

    def test_unknown_tool_falls_through_to_text_response(self):
        widget_id, params = resolve_intent(["non_existent_tool_xyz"], "u1")
        assert widget_id == WidgetId.TEXT_RESPONSE
        assert params == {}


class TestResolveIntentBackwardCompat:
    def test_two_arg_call_omitting_tool_data_works(self):
        """resolve_intent(tools, user_id) — third arg optional; must not raise."""
        widget_id, params = resolve_intent(["get_portfolio_summary"], "u99")
        assert widget_id == WidgetId.PORTFOLIO_SUMMARY
        assert params["userId"] == "u99"
        assert "data" not in params

    def test_two_arg_call_empty_tools(self):
        widget_id, params = resolve_intent([], "u99")
        assert widget_id == WidgetId.TEXT_RESPONSE
        assert params == {}
