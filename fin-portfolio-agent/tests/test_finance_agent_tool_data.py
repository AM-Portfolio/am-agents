"""Tool payload merge + fallback when MCP returns holdings but LLM answer is blank."""
import json

from langchain_core.messages import ToolMessage

from shared.agents.finance_agent import (
    _extract_tool_data,
    _merge_tool_data,
    _parse_tool_result,
)
from shared.formatters.tool_fallback import build_tool_fallback_answer, needs_tool_fallback


def _double_encoded_holdings(count: int = 106) -> str:
    inner = {
        "holdings": [{"symbol": "RELIANCE"}, {"symbol": "TCS"}],
        "count": count,
    }
    return json.dumps(json.dumps(inner))


def test_parse_tool_result_unwraps_double_encoded_json():
    parsed = _parse_tool_result(_double_encoded_holdings())
    assert isinstance(parsed, dict)
    assert parsed["count"] == 106
    assert len(parsed["holdings"]) == 2


def test_extract_tool_data_from_tool_message():
    tm = ToolMessage(
        tool_call_id="x",
        content=_double_encoded_holdings(),
        name="get_holdings_list",
    )
    data = _extract_tool_data([tm])
    assert "get_holdings_list" in data
    assert data["get_holdings_list"]["count"] == 106


def test_merge_tool_data_prefers_state_then_messages():
    tm = ToolMessage(
        tool_call_id="x",
        content=_double_encoded_holdings(42),
        name="get_holdings_list",
    )
    final_state = {
        "tool_data": {"get_portfolio_summary": {"totalValue": 1}},
        "messages": [tm],
    }
    merged = _merge_tool_data(final_state, "unused-trace")
    assert merged["get_portfolio_summary"]["totalValue"] == 1
    assert merged["get_holdings_list"]["count"] == 42


def test_holdings_fallback_from_extracted_double_encoded_payload():
    tm = ToolMessage(
        tool_call_id="x",
        content=_double_encoded_holdings(),
        name="get_holdings_list",
    )
    tool_data = _extract_tool_data([tm])
    answer = "I couldn't find a specific answer for that."
    tools = ["get_holdings_list"]
    assert needs_tool_fallback(answer, tools)
    fallback = build_tool_fallback_answer(tools, tool_data)
    assert fallback
    assert "106 holdings" in fallback
    assert "RELIANCE" in fallback
