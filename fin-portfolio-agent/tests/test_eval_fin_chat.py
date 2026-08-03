"""Unit tests for golden eval thick evaluators (no network)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from eval_fin_chat import evaluate_item  # noqa: E402


class TestEvaluateItem:
    def test_pass_portfolio_summary_artifact(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "portfolio.summary.v1",
                "data": {"total": 1},
                "toolsUsed": ["get_portfolio_summary"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "artifactType": "portfolio.summary.v1",
                "requireToolsUsed": True,
                "requiredToolsAny": ["get_portfolio_summary"],
                "forbidTools": ["ask_finance_agent"],
            },
        )
        assert failures == []

    def test_fail_wrong_artifact(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "text.v1",
                "toolsUsed": ["get_portfolio_summary"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "artifactType": "portfolio.summary.v1",
                "requireToolsUsed": True,
            },
        )
        assert any("artifactType" in f for f in failures)

    def test_fail_forbidden_tool(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "portfolio.summary.v1",
                "toolsUsed": ["get_portfolio_summary", "ask_finance_agent"],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "artifactType": "portfolio.summary.v1",
                "requireToolsUsed": True,
                "forbidTools": ["ask_finance_agent"],
            },
        )
        assert any("forbidden" in f for f in failures)

    def test_hello_no_tools(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "text.v1",
                "toolsUsed": [],
                "traceId": "abc",
                "sessionId": "s1",
            },
            expected={
                "artifactType": "text.v1",
                "requireToolsUsed": False,
            },
        )
        assert failures == []

    def test_fail_http(self):
        failures = evaluate_item(
            status_code=500,
            body={},
            expected={"artifactType": "text.v1"},
        )
        assert any("http_status" in f for f in failures)

    def test_required_data_keys(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "holdings.list.v1",
                "data": {"holdings": [{"symbol": "X"}], "count": 1},
                "toolsUsed": ["get_holdings"],
                "traceId": "t",
                "sessionId": "s",
            },
            expected={
                "artifactType": "holdings.list.v1",
                "requiredDataKeys": ["holdings", "count"],
            },
        )
        assert failures == []

    def test_required_data_keys_missing(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "holdings.list.v1",
                "data": {},
                "toolsUsed": ["get_holdings"],
                "traceId": "t",
                "sessionId": "s",
            },
            expected={
                "artifactType": "holdings.list.v1",
                "requiredDataKeys": ["holdings", "count"],
            },
        )
        assert any("data[" in f for f in failures)

    def test_required_data_keys_any(self):
        failures = evaluate_item(
            status_code=200,
            body={
                "artifactType": "portfolio.movers.v1",
                "data": {"movers": [{"symbol": "A"}]},
                "toolsUsed": ["get_top_movers"],
                "traceId": "t",
                "sessionId": "s",
            },
            expected={
                "artifactType": "portfolio.movers.v1",
                "requiredDataKeysAny": ["gainers", "movers"],
            },
        )
        assert failures == []
