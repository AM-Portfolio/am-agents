"""Unit tests for synthetic tool-call parsing from LLM text."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.agents.finance_agent import (
    _looks_like_invented_tools_only,
    _parse_text_tool_calls,
)
from shared.clients.am_mcp_client import _unwrap_mcp_envelope


def _tools(*names: str):
    return [
        {"type": "function", "function": {"name": n, "parameters": {"type": "object"}}}
        for n in names
    ]


def test_parses_markdown_json_with_tool_key():
    text = (
        'I will retrieve your holdings.\n\n'
        '```json\n'
        '{\n  "tool": "get_holdings",\n  "arguments": {}\n}\n'
        '```'
    )
    calls = _parse_text_tool_calls(text, _tools("get_holdings", "get_portfolio_summary"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_holdings"
    assert calls[0]["function"]["arguments"] == "{}"


def test_parses_markdown_json_with_name_key():
    text = '```json\n{"name":"get_portfolio_summary","arguments":{"portfolioId":"p1"}}\n```'
    calls = _parse_text_tool_calls(text, _tools("get_portfolio_summary"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_portfolio_summary"
    args = json.loads(calls[0]["function"]["arguments"])
    assert args.get("portfolioId") == "p1"


def test_parses_bare_json_tool_key():
    text = '{"tool":"get_holdings","arguments":{}}'
    calls = _parse_text_tool_calls(text, _tools("get_holdings"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_holdings"


def test_parses_parameters_alias():
    text = '```json\n{"tool":"get_holdings","parameters":{"portfolioId":"abc"}}\n```'
    calls = _parse_text_tool_calls(text, _tools("get_holdings"))
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert args.get("portfolioId") == "abc"


def test_parses_tool_code_xml_json():
    text = '<tool_code>{"name":"get_top_movers","arguments":{}}</tool_code>'
    calls = _parse_text_tool_calls(text, _tools("get_top_movers"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_top_movers"


def test_parses_tool_code_name_only():
    text = '<tool_code>get_market_movers</tool_code>'
    calls = _parse_text_tool_calls(text, _tools("get_market_movers"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_market_movers"


def test_rejects_unknown_markdown_tool():
    text = '```json\n{"tool":"web_search","arguments":{}}\n```'
    calls = _parse_text_tool_calls(text, _tools("get_holdings"))
    assert calls == []


def test_known_line_tool_call():
    calls = _parse_text_tool_calls("get_holdings()", _tools("get_holdings"))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_holdings"


def test_invented_line_tools_soft_refuse():
    text = "get_holdings_list()\nget_holding_details()"
    tools = _tools("get_holdings", "get_portfolio_summary")
    assert _looks_like_invented_tools_only(text, tools) is True
    assert _parse_text_tool_calls(text, tools) == []


def test_unwrap_success_returns_data():
    assert _unwrap_mcp_envelope({"ok": True, "data": {"holdings": [1]}}) == {"holdings": [1]}


def test_unwrap_response_too_large():
    out = _unwrap_mcp_envelope({
        "ok": False,
        "error": "RESPONSE_TOO_LARGE",
        "message": "too big",
        "tool": "get_holdings",
    })
    assert out["error"] == "RESPONSE_TOO_LARGE"
    assert out["tool"] == "get_holdings"
