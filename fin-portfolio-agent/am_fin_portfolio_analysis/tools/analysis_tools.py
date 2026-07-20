"""
Analysis Domain Tools — using REST client (Phase H.5)
Data from am-analysis REST API (port 8060).
ETF overlap still uses core/engine.py (MongoDB) as that's where ETF DB lives.
"""
import json
import logging
from shared.context.request_context import user_id_var
from shared.tools.registry import register_tool
from ..clients.analysis_client import analysis_client
from ..core.engine import engine
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

logger = logging.getLogger(__name__)


def _format(data, label: str) -> str:
    if isinstance(data, dict) and "error" in data:
        return f"Error retrieving {label}: {data['error']}."
    return f"{label}:\n{json.dumps(data, indent=2)}"


@register_tool(
    description="Get top gainers and losers in the user's portfolio today.",
    parameters={
        "type": "object",
        "properties": {
            "time_frame": {"type": "string", "description": "DAY or TOTAL (default: DAY)"}
        },
        "required": []
    }
)
def get_top_movers(time_frame: str = "DAY") -> str:
    data = analysis_client.get_top_movers(time_frame=time_frame)
    return _format(data, "Top Movers")


@register_tool(
    description="Get the sector/asset allocation breakdown of the user's portfolio.",
    parameters={"type": "object", "properties": {}, "required": []}
)
def get_sector_allocation() -> str:
    data = analysis_client.get_sector_allocation()
    return _format(data, "Sector Allocation")


@register_tool(
    description="Calculate the true portfolio overlap between a specific ETF and the user's direct stocks.",
    parameters={
        "type": "object",
        "properties": {
            "etf_symbol": {"type": "string", "description": "ETF symbol or name (e.g., 'NIFTYBEES')"}
        },
        "required": ["etf_symbol"]
    }
)
def analyze_etf_overlap(etf_symbol: str) -> str:
    if not etf_symbol:
        return "Error: No ETF symbol provided."
    try:
        result = engine.calculate_etf_overlap(etf_symbol)
        return _format(result, f"ETF Overlap — {etf_symbol}")
    except Exception as e:
        return f"Error analyzing ETF overlap: {e}"


@register_tool(
    description="Count the number of ETFs in the user's portfolio.",
    parameters={"type": "object", "properties": {}, "required": []}
)
def count_etfs() -> str:
    data = analysis_client.get_holdings()
    if isinstance(data, dict) and "error" in data:
        return _format(data, "ETF count")
    holdings = data if isinstance(data, list) else data.get("holdings", [])
    etfs = [h for h in holdings if str(h.get("isin", "")).startswith("INF")]
    if not etfs:
        return "You have 0 ETFs in your portfolio."
    etf_list = [f"  - {h.get('symbol', 'N/A')} (ISIN: {h.get('isin', 'N/A')})" for h in etfs]
    return f"You have {len(etfs)} ETF(s):\n" + "\n".join(etf_list)


@register_tool(
    description="Get details about an ETF or Mutual Fund in the portfolio.",
    parameters={
        "type": "object",
        "properties": {
            "fund_name": {"type": "string", "description": "ETF or fund name/symbol"}
        },
        "required": ["fund_name"]
    }
)
def get_fund_details(fund_name: str) -> str:
    try:
        etf = engine.get_etf_details(fund_name)
        if etf:
            return f"ETF Details:\n{json.dumps(etf, indent=2)}"
        mf = engine.get_mf_details(fund_name)
        if mf:
            return f"Mutual Fund Details:\n{json.dumps(mf, indent=2)}"
        return f"Fund '{fund_name}' not found."
    except Exception as e:
        return f"Error fetching fund details: {e}"


@register_tool(
    description="Search the live internet for stock news, market trends, or financial information.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
)
def web_search(query: str) -> str:
    try:
        results = []
        with DDGS() as ddgs:
            try:
                for r in ddgs.text(query, max_results=5):
                    results.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
            except DuckDuckGoSearchException as e:
                if "Ratelimit" in str(e):
                    return "Search engine is rate-limited. Please try again in a few minutes."
                raise
            if len(results) < 2:
                for r in ddgs.news(query, max_results=5):
                    results.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
        if not results:
            return f"No results found for '{query}'."
        return f"Web results for '{query}':\n{json.dumps(results, indent=2)}"
    except Exception as e:
        return f"Web search error: {e}"
