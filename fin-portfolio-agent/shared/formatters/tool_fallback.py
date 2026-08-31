"""Deterministic user-facing text when the LLM returns blank after MCP tools ran."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.formatters.tool_payload import normalize_portfolio_summary, unwrap_tool_payload

_GENERIC_MISS_FRAGMENTS = (
    "I couldn't find a specific answer for that.",
    "I'm working on fetching that information",
    "I couldn't complete that request",
)


def needs_tool_fallback(answer: str, tools_called: List[str]) -> bool:
    if not tools_called:
        return False
    text = (answer or "").strip()
    if not text:
        return True
    return any(fragment in text for fragment in _GENERIC_MISS_FRAGMENTS)


def _fmt_inr(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"₹{num:,.2f}"


def _tool_error(payload: Any) -> Optional[str]:
    data = unwrap_tool_payload(payload)
    if isinstance(data, dict):
        if data.get("error"):
            return f"I couldn't fetch that data: {data.get('error')}"
        if data.get("ok") is False:
            return f"I couldn't fetch that data: {data.get('message') or data.get('error') or 'unknown error'}"
    return None


def _holdings_symbols(payload: Any, limit: int = 5) -> List[str]:
    data = unwrap_tool_payload(payload)
    if not isinstance(data, dict):
        return []
    holdings = data.get("holdings") or data.get("items") or []
    if not isinstance(holdings, list):
        return []
    symbols: List[str] = []
    for row in holdings[:limit]:
        if isinstance(row, dict):
            sym = row.get("symbol") or row.get("sourceId") or row.get("name")
            if sym:
                symbols.append(str(sym))
    return symbols


def build_tool_fallback_answer(
    tools_called: List[str],
    tool_data: Dict[str, Any],
) -> Optional[str]:
    """Build a short en-IN answer from the last meaningful tool result."""
    if not tools_called or not tool_data:
        return None

    for name in reversed(tools_called):
        if name not in tool_data:
            continue
        raw = tool_data[name]
        err = _tool_error(raw)
        if err:
            return err

        data = unwrap_tool_payload(raw)
        if not isinstance(data, dict):
            continue

        if name in ("get_portfolio_summary",):
            norm = normalize_portfolio_summary(data)
            current = norm.get("totalValue") or norm.get("currentValue")
            invested = norm.get("totalInvested") or norm.get("investmentValue")
            holdings = norm.get("totalHoldings") or norm.get("totalAssets")
            parts = ["Here is your portfolio summary."]
            if current is not None:
                parts.append(f"Current value: {_fmt_inr(current)}.")
            if invested is not None:
                parts.append(f"Invested: {_fmt_inr(invested)}.")
            if holdings is not None:
                parts.append(f"Holdings count: {holdings}.")
            return " ".join(parts)

        if name in ("get_holdings_list", "get_holdings"):
            holdings = data.get("holdings") or data.get("items") or []
            count = data.get("count") or data.get("totalAssets") or len(holdings)
            syms = _holdings_symbols(data)
            if count:
                tail = f" Top symbols: {', '.join(syms)}." if syms else ""
                return f"You have {count} holdings in your portfolio.{tail}"
            return "You have no holdings on record."

        if name == "get_sector_allocation":
            sectors = data.get("sectorAllocation") or {}
            if isinstance(sectors, dict) and sectors:
                top = sorted(sectors.items(), key=lambda kv: kv[1], reverse=True)[:5]
                parts = [f"{k}: {v}" for k, v in top]
                return f"Your portfolio sector exposure — {', '.join(parts)}."
            return "No sector allocation data is available for your portfolio."

        if name == "get_market_cap_allocation":
            caps = data.get("marketCapAllocation") or {}
            if isinstance(caps, dict) and caps:
                parts = [f"{k}: {v}" for k, v in caps.items()]
                return f"Your market cap breakdown — {', '.join(parts)}."
            return "No market cap allocation data is available."

        if name == "get_top_movers":
            gainers = data.get("gainers") or []
            losers = data.get("losers") or []
            if not gainers and not losers:
                return "No ranked gainers or losers in your portfolio right now."
            g_syms = [str(g.get("symbol", "")) for g in gainers[:3] if isinstance(g, dict) and g.get("symbol")]
            l_syms = [str(l.get("symbol", "")) for l in losers[:3] if isinstance(l, dict) and l.get("symbol")]
            parts = []
            if g_syms:
                parts.append(f"Top gainers: {', '.join(g_syms)}")
            if l_syms:
                parts.append(f"Top losers: {', '.join(l_syms)}")
            return "Your portfolio movers — " + "; ".join(parts) + "."

        if name == "get_market_movers":
            movers = data.get("movers") or []
            if not movers:
                return "No market movers are available right now."
            syms = [
                str(m.get("symbol") or m.get("name") or "")
                for m in movers[:5]
                if isinstance(m, dict)
            ]
            syms = [s for s in syms if s]
            if syms:
                return f"Market movers include: {', '.join(syms)}."
            return f"Found {len(movers)} market movers."

        if name == "get_recent_activity":
            activities = data.get("activities") or []
            count = data.get("count") or len(activities)
            if not count:
                return "You have no recent trade activity on record."
            return f"You have {count} recent transaction(s). See the activity panel for details."

        if name == "get_trade_history":
            trades = data.get("activities") or data.get("trades") or []
            if isinstance(trades, list) and trades:
                return f"Found {len(trades)} trade(s) for that symbol."
            return "No trades found for that symbol."

        if name == "get_stock_quote":
            price = data.get("ltp") or data.get("lastPrice") or data.get("price")
            symbol = data.get("symbol") or data.get("tradingsymbol")
            if price is not None and symbol:
                return f"{symbol} is trading at {_fmt_inr(price)}."
            if price is not None:
                return f"Current price: {_fmt_inr(price)}."

        if name == "get_indices_data":
            indices = data.get("indices") or data
            if isinstance(indices, dict) and indices:
                parts = []
                for key, val in list(indices.items())[:3]:
                    if isinstance(val, dict):
                        level = val.get("last") or val.get("ltp") or val.get("value")
                        if level is not None:
                            parts.append(f"{key}: {_fmt_inr(level)}")
                    elif val is not None:
                        parts.append(f"{key}: {val}")
                if parts:
                    return "Index levels — " + ", ".join(parts) + "."

    return None
