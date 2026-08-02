"""Unit tests for golden eval thick evaluators (no network)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from eval_fin_chat import evaluate_item  # noqa: E402


class TestEvaluateItem:
    def test_pass_portfolio_summary(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "widgetId": "PORTFOLIO_SUMMARY",
                "widgetParams": {"userId": "u1", "data": {"total": 1}},
                "toolsUsed": ["get_portfolio_summary"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "widgetId": "PORTFOLIO_SUMMARY",
                "requiredWidgetParams": ["userId"],
                "requireToolsUsed": True,
                "requiredToolsAny": ["get_portfolio_summary"],
            },
        )
        assert failures == []

    def test_fail_wrong_widget(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "widgetId": "TEXT_RESPONSE",
                "widgetParams": {"userId": "u1"},
                "toolsUsed": ["get_portfolio_summary"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "widgetId": "PORTFOLIO_SUMMARY",
                "requiredWidgetParams": ["userId"],
                "requireToolsUsed": True,
            },
        )
        assert any("widgetId" in f for f in failures)

    def test_fail_empty_userid(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "widgetId": "HOLDINGS_TABLE",
                "widgetParams": {"userId": ""},
                "toolsUsed": ["get_holdings_list"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "widgetId": "HOLDINGS_TABLE",
                "requiredWidgetParams": ["userId"],
                "requireToolsUsed": True,
            },
        )
        assert any("userId" in f for f in failures)

    def test_hello_no_tools(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "widgetId": "TEXT_RESPONSE",
                "widgetParams": {},
                "toolsUsed": [],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "widgetId": "TEXT_RESPONSE",
                "requiredWidgetParams": [],
                "requireToolsUsed": False,
            },
        )
        assert failures == []

    def test_http_error(self):
        failures = evaluate_item(
            status_code=500,
            body={},
            expected={"widgetId": "PORTFOLIO_SUMMARY"},
        )
        assert any("http_status" in f for f in failures)
