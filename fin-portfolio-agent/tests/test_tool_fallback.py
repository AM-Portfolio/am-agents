"""Wave B: fallback text when MCP returned data but LLM answer is blank."""
from shared.formatters.tool_fallback import build_tool_fallback_answer, needs_tool_fallback


def test_needs_fallback_on_empty_answer_with_tools():
    assert needs_tool_fallback("", ["get_holdings_list"])
    assert needs_tool_fallback("I couldn't find a specific answer for that.", ["get_holdings_list"])


def test_holdings_fallback_non_empty():
    payload = {
        "holdings": [
            {"symbol": "RELIANCE", "qty": 10},
            {"symbol": "TCS", "qty": 5},
        ],
        "count": 2,
    }
    answer = build_tool_fallback_answer(["get_holdings_list"], {"get_holdings_list": payload})
    assert answer
    assert "2 holdings" in answer
    assert "RELIANCE" in answer


def test_summary_fallback_uses_inr():
    payload = {"currentValue": 832786.37, "investmentValue": 800000, "totalAssets": 106}
    answer = build_tool_fallback_answer(["get_portfolio_summary"], {"get_portfolio_summary": payload})
    assert answer
    assert "₹" in answer
    assert "832" in answer


def test_empty_portfolio_movers_honest():
    payload = {"gainers": [], "losers": []}
    answer = build_tool_fallback_answer(["get_top_movers"], {"get_top_movers": payload})
    assert answer
    assert "No ranked" in answer
