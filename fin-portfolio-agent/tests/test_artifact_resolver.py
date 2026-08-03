"""Unit tests for artifact_resolver."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.formatters.artifact_resolver import resolve_artifact


class TestResolveArtifact:
    def test_empty_tools_is_text(self):
        assert resolve_artifact([]) == ("text.v1", None)

    def test_known_tool(self):
        data = {"get_portfolio_summary": {"totalValue": 1}}
        artifact, payload = resolve_artifact(["get_portfolio_summary"], data)
        assert artifact == "portfolio.summary.v1"
        assert payload == {"totalValue": 1}

    def test_prefers_last_known_tool(self):
        data = {
            "get_portfolio_summary": {"a": 1},
            "get_holdings": {"b": 2},
        }
        artifact, payload = resolve_artifact(
            ["get_portfolio_summary", "get_holdings"], data
        )
        assert artifact == "holdings.list.v1"
        assert payload == {"b": 2}

    def test_error_payload(self):
        data = {"get_portfolio_summary": {"error": "MCP_UNAVAILABLE"}}
        artifact, payload = resolve_artifact(["get_portfolio_summary"], data)
        assert artifact == "error.v1"
        assert payload["error"] == "MCP_UNAVAILABLE"

    def test_unknown_tool_generic(self):
        data = {"custom_tool": {"x": 1}}
        artifact, payload = resolve_artifact(["custom_tool"], data)
        assert artifact == "data.generic.v1"
        assert payload == {"x": 1}

    def test_holdings_slim_payload(self):
        data = {
            "get_holdings": {
                "count": 2,
                "truncated": False,
                "holdings": [
                    {"symbol": "RELIANCE", "currentValue": 100},
                    {"symbol": "TCS", "currentValue": 90},
                ],
            }
        }
        artifact, payload = resolve_artifact(["get_holdings"], data)
        assert artifact == "holdings.list.v1"
        assert payload["count"] == 2
        assert len(payload["holdings"]) == 2

    def test_trades_and_quote_artifacts(self):
        assert resolve_artifact(
            ["get_recent_activity"],
            {"get_recent_activity": {"activities": [], "count": 0}},
        )[0] == "trades.recent.v1"
        assert resolve_artifact(
            ["get_stock_quote"],
            {"get_stock_quote": {"symbol": "RELIANCE", "ltp": 1}},
        )[0] == "market.quote.v1"
