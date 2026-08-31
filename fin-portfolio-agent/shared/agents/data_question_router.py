"""Keyword router: map data questions to MCP tools when the LLM skips tool_choice."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, Optional, Tuple

_GREETING = re.compile(
    r"^\s*(hi|hey|hello|good\s+(morning|afternoon|evening)|howdy)\b",
    re.IGNORECASE,
)

_BASKET = re.compile(
    r"\b(list|show|my|investment)?\s*baskets?\b|\binvestment\s+baskets?\b",
    re.IGNORECASE,
)

BASKET_UNAVAILABLE_REPLY = (
    "Investment baskets aren't available in chat yet. "
    "Open the Baskets section in the app to view or manage them."
)

# (pattern, tool_name, arg_builder)
# Order matters: more specific rules first.
_RULES: list[tuple[re.Pattern[str], str, Optional[str]]] = [
    (
        re.compile(r"\b(nifty|sensex|banknifty|market)\s+(gainers|losers|movers)\b", re.I),
        "get_market_movers",
        None,
    ),
    (
        re.compile(r"\bmarket\s+movers\b", re.I),
        "get_market_movers",
        None,
    ),
    (
        re.compile(
            r"\b(my|portfolio)\s+(best|top|worst)\s+(perform|gainer|loser|stock|holding)",
            re.I,
        ),
        "get_top_movers",
        None,
    ),
    (
        re.compile(r"\bmy\s+(gainers|losers|best\s+perform|worst\s+perform)\b", re.I),
        "get_top_movers",
        None,
    ),
    (
        re.compile(r"\b(recent\s+activity|last\s+trades?|transactions?|what\s+did\s+i\s+buy)\b", re.I),
        "get_recent_activity",
        None,
    ),
    (
        re.compile(r"\b(sector\s+allocation|sector\s+exposure|diversif|what\s+sectors)\b", re.I),
        "get_sector_allocation",
        None,
    ),
    (
        re.compile(r"\b(market\s+cap|large\s+cap|mid\s+cap|small\s+cap)\b", re.I),
        "get_market_cap_allocation",
        None,
    ),
    (
        re.compile(r"\b(portfolio\s+summary|dashboard|net\s+worth|total\s+value)\b", re.I),
        "get_portfolio_summary",
        None,
    ),
    (
        re.compile(r"\b(holdings|what\s+do\s+i\s+hold|list\s+(all\s+)?my\s+stock)\b", re.I),
        "get_holdings_list",
        None,
    ),
    (
        re.compile(r"\b(where\s+is\s+)?(nifty|sensex|banknifty)\b", re.I),
        "get_indices_data",
        None,
    ),
    (
        re.compile(
            r"(?:price\s+of|quote\s+for|current\s+price\s+of)\s+([A-Z][A-Z0-9&.-]{1,20})",
            re.I,
        ),
        "get_stock_quote",
        "symbol",
    ),
    (
        re.compile(r"\bwhat\s+is\s+([A-Z][A-Z0-9&.-]{2,20})\s+trading\s+at\b", re.I),
        "get_stock_quote",
        "symbol",
    ),
    (
        re.compile(r"\b([A-Z][A-Z0-9&.-]{2,20})\s+(?:price|quote|ltp|trading\s+at)\b", re.I),
        "get_stock_quote",
        "symbol",
    ),
    (
        re.compile(r"\btrade\s+history\b.*\b([A-Z][A-Z0-9&.-]{2,20})\b", re.I),
        "get_trade_history",
        "symbol",
    ),
    (
        re.compile(
            r"\b(?:find|search|look\s+up)\s+(?:for\s+)?(.+?)\s+(?:stock|stocks|etf|etfs|symbol)\b",
            re.I,
        ),
        "search_instruments",
        "query",
    ),
    (
        re.compile(r"\b(?:find|search)\s+(?:stock|stocks|etf|etfs)\s+(?:for|named|like)?\s*(.+)", re.I),
        "search_instruments",
        "query",
    ),
]


def is_greeting(text: str) -> bool:
    return bool(_GREETING.match(text.strip()))


def match_static_reply(text: str) -> Optional[str]:
    """Deterministic chat answers that must not invoke the LLM or phantom tools."""
    if not text or not text.strip():
        return None
    if is_greeting(text):
        return None
    if _BASKET.search(text):
        return BASKET_UNAVAILABLE_REPLY
    return None


def match_data_question(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Return (agent_tool_name, args) for a forced first-turn tool call, or None.
    """
    if not text or not text.strip():
        return None
    if is_greeting(text):
        return None

    for pattern, tool_name, capture in _RULES:
        m = pattern.search(text)
        if not m:
            continue
        args: Dict[str, Any] = {}
        if capture == "symbol" and m.lastindex:
            args["symbol"] = m.group(m.lastindex).upper()
        if capture == "query" and m.lastindex:
            query = m.group(m.lastindex).strip().strip("?.!")
            if query:
                args["query"] = query
            else:
                continue
        if tool_name == "get_recent_activity":
            args.setdefault("limit", 20)
        if tool_name == "get_market_movers":
            args.setdefault("limit", 10)
            args.setdefault("type", "GAINERS")
            if re.search(r"\b(sensex)\b", text, re.I):
                args.setdefault("indexSymbol", "SENSEX")
            elif re.search(r"\b(banknifty|bank\s+nifty)\b", text, re.I):
                args.setdefault("indexSymbol", "NIFTY BANK")
            elif re.search(r"\b(nifty|market)\b", text, re.I):
                args.setdefault("indexSymbol", "NIFTY 50")
            if re.search(r"\blosers?\b", text, re.I):
                args["type"] = "LOSERS"
        return tool_name, args

    return None


def build_forced_tool_call(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """OpenAI-style assistant message with a single tool_call."""
    return {
        "content": "",
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(args),
                },
            }
        ],
    }
