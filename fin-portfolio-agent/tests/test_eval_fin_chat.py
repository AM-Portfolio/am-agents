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
