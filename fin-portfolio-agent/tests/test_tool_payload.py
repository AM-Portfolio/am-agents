"""Tests for MCP/analysis payload normalization."""
import json

from shared.formatters.tool_payload import normalize_portfolio_summary, normalize_tool_payload


def test_unwrap_ok_data_envelope_string():
    raw = json.dumps(
        {
            "ok": True,
            "data": {
                "investmentValue": 100.0,
                "currentValue": 110.0,
                "totalGainLoss": 10.0,
            },
        }
    )
    out = normalize_portfolio_summary(raw)
    assert out["totalInvested"] == 100.0
    assert out["totalValue"] == 110.0
    assert out["totalGainLoss"] == 10.0


def test_unwrap_ok_data_envelope_dict():
    raw = {
        "ok": True,
        "data": {
            "investmentValue": 53067494.33,
            "currentValue": 53067494.33,
            "totalGainLoss": 0.0,
            "totalGainLossPercentage": 0.0,
            "todayGainLoss": 0.0,
            "todayGainLossPercentage": 0.0,
            "totalAssets": 1,
            "brokers": ["ZERODHA"],
        },
    }
    out = normalize_tool_payload("get_portfolio_summary", raw)
    assert out["totalValue"] == 53067494.33
    assert out["totalInvested"] == 53067494.33
    assert out["totalHoldings"] == 1
    assert out["brokers"] == ["ZERODHA"]
