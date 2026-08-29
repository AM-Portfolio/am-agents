"""Normalize MCP / analysis tool payloads for Flutter widgetParams."""
from __future__ import annotations

import json
from typing import Any


def _parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return value


def unwrap_tool_payload(raw: Any) -> Any:
    """Parse JSON strings and unwrap {ok, data} MCP envelopes."""
    payload = _parse_json_maybe(raw)
    if isinstance(payload, dict) and "raw" in payload and len(payload) == 1:
        payload = _parse_json_maybe(payload["raw"])

    if isinstance(payload, dict) and payload.get("ok") is True and "data" in payload:
        inner = _parse_json_maybe(payload["data"])
        return inner if inner is not None else payload

    if isinstance(payload, dict) and "error" in payload and len(payload) <= 3:
        return payload

    return payload


def normalize_portfolio_summary(raw: Any) -> dict[str, Any]:
    """Map analysis / MCP summary fields to ai_widget_factory PORTFOLIO_SUMMARY shape."""
    payload = unwrap_tool_payload(raw)
    if not isinstance(payload, dict):
        return {"raw": str(payload)}

    if "portfolios" in payload and isinstance(payload.get("portfolios"), list):
        return payload

    portfolio_keys = {
        "investmentValue", "currentValue", "totalValue", "totalInvested",
        "totalGainLoss", "totalGainLossPercentage", "todayGainLoss",
        "todayGainLossPercentage", "totalAssets", "totalHoldings",
    }
    if not any(key in payload for key in portfolio_keys):
        return payload
    current = payload.get("currentValue", payload.get("totalValue"))
    invested = payload.get("investmentValue", payload.get("totalInvested"))
    day_change = payload.get("todayGainLoss", payload.get("dayChange"))
    day_change_pct = payload.get("todayGainLossPercentage", payload.get("dayChangePercentage"))

    normalized: dict[str, Any] = {
        "totalValue": current,
        "totalInvested": invested,
        "totalGainLoss": payload.get("totalGainLoss"),
        "totalGainLossPercentage": payload.get("totalGainLossPercentage"),
        "dayChange": day_change,
        "dayChangePercentage": day_change_pct,
        "totalHoldings": payload.get("totalAssets", payload.get("totalHoldings")),
        "totalPortfolios": payload.get("totalPortfolios", 1),
        "gainersCount": payload.get("gainersCount"),
        "losersCount": payload.get("losersCount"),
        "lastUpdated": payload.get("lastUpdated"),
        "brokers": payload.get("brokers"),
    }
    return {**payload, **{k: v for k, v in normalized.items() if v is not None}}


def normalize_tool_payload(tool_name: str, raw: Any) -> Any:
    """Return widget-ready data for a tool result."""
    if tool_name == "get_portfolio_summary":
        return normalize_portfolio_summary(raw)
    return unwrap_tool_payload(raw)
