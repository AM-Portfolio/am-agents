"""
Tests for the tool-data extraction loop that lives inside
agents/finance_agent.py — FinanceAgent.chat().

We do NOT import finance_agent (it triggers heavy LangGraph / LLM imports).
Instead the exact loop logic is copied here as a local helper so we can test
the algorithm in pure isolation.

Extraction loop (copied verbatim from finance_agent.py lines 225-233):

    tool_data: dict = {}
    for msg in final_state.get("messages", []):
        msg_type = getattr(msg, "type", None)
        msg_name = getattr(msg, "name", None)
        content   = getattr(msg, "content", None)
        if msg_type == "tool" and msg_name and content:
            try:
                tool_data[msg_name] = json.loads(content)
            except (ValueError, TypeError):
                tool_data[msg_name] = {"raw": str(content)}

Covers:
- ToolMessage.type == "tool" (LangChain contract)
- JSON content → dict parsed correctly
- Multiple tools → all collected by name
- Non-JSON plain text → {"raw": content}
- Error string (starts with "Error retrieving") → {"raw": ...}
- HumanMessage → skipped
- AIMessage → skipped
- Plain object with no 'type' attr → skipped
- ToolMessage with empty content "" → skipped
- mixed_message_list fixture → result has only "get_portfolio_summary" key
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage


# ─── local helper: exact copy of extraction loop ─────────────────────────────

def _extract_tool_data(messages: list) -> dict:
    """Mirrors the tool_data extraction loop in FinanceAgent.chat()."""
    tool_data: dict = {}
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        msg_name = getattr(msg, "name", None)
        content = getattr(msg, "content", None)
        if msg_type == "tool" and msg_name and content:
            try:
                tool_data[msg_name] = json.loads(content)
            except (ValueError, TypeError):
                tool_data[msg_name] = {"raw": str(content)}
    return tool_data


# ─── helpers ─────────────────────────────────────────────────────────────────

def _tool_msg(name: str, content: str, tool_call_id: str = "call_1") -> ToolMessage:
    return ToolMessage(tool_call_id=tool_call_id, content=content, name=name)


# ─── tests ───────────────────────────────────────────────────────────────────

class TestToolMessageLangChainContract:
    def test_tool_message_type_is_tool(self):
        """LangChain ToolMessage must have .type == 'tool' for the loop to work."""
        msg = _tool_msg("some_tool", '{"k": 1}')
        assert msg.type == "tool"

    def test_human_message_type_is_human(self):
        assert HumanMessage(content="hi").type == "human"

    def test_ai_message_type_is_ai(self):
        assert AIMessage(content="hi").type == "ai"


class TestExtractToolDataJsonContent:
    def test_json_content_parsed_to_dict(self):
        payload = {"totalValue": 1_500_000, "holdings": 15}
        msg = _tool_msg("get_portfolio_summary", json.dumps(payload))
        result = _extract_tool_data([msg])
        assert result["get_portfolio_summary"] == payload

    def test_nested_json_round_trips(self):
        payload = {"summary": {"best": "RELIANCE", "worst": "INFY"}}
        msg = _tool_msg("get_portfolio_summary", json.dumps(payload))
        result = _extract_tool_data([msg])
        assert result["get_portfolio_summary"]["summary"]["best"] == "RELIANCE"

    def test_multiple_tools_all_collected(self):
        payload_a = {"items": [1, 2, 3]}
        payload_b = {"sector": "Tech", "pct": 35}
        msgs = [
            _tool_msg("get_holdings_list", json.dumps(payload_a), tool_call_id="c1"),
            _tool_msg("get_sector_allocation", json.dumps(payload_b), tool_call_id="c2"),
        ]
        result = _extract_tool_data(msgs)
        assert result["get_holdings_list"] == payload_a
        assert result["get_sector_allocation"] == payload_b

    def test_only_tool_messages_collected(self):
        msgs = [
            HumanMessage(content="Show portfolio"),
            _tool_msg("get_portfolio_summary", '{"v": 1}'),
            AIMessage(content="Here it is"),
        ]
        result = _extract_tool_data(msgs)
        assert set(result.keys()) == {"get_portfolio_summary"}


class TestExtractToolDataNonJsonContent:
    def test_plain_text_becomes_raw_dict(self):
        msg = _tool_msg("web_search", "Some plain text result")
        result = _extract_tool_data([msg])
        assert result["web_search"] == {"raw": "Some plain text result"}

    def test_error_string_becomes_raw_dict(self):
        error_str = "Error retrieving Portfolio Summary: Connection refused. Make sure am-analysis is running on port 8060."
        msg = _tool_msg("get_portfolio_summary", error_str)
        result = _extract_tool_data([msg])
        assert result["get_portfolio_summary"] == {"raw": error_str}

    def test_integer_string_parses_as_json_number(self):
        """json.loads("42") succeeds and returns int — not treated as non-JSON."""
        msg = _tool_msg("some_tool", "42")
        result = _extract_tool_data([msg])
        assert result["some_tool"] == 42


class TestExtractToolDataSkippedMessages:
    def test_human_message_skipped(self):
        msgs = [HumanMessage(content="What is my portfolio?")]
        assert _extract_tool_data(msgs) == {}

    def test_ai_message_skipped(self):
        msgs = [AIMessage(content="Here is your summary.")]
        assert _extract_tool_data(msgs) == {}

    def test_plain_object_no_type_attr_skipped(self):
        class NoTypeObj:
            name = "something"
            content = '{"x": 1}'

        assert _extract_tool_data([NoTypeObj()]) == {}

    def test_tool_message_empty_content_skipped(self):
        """Empty string is falsy — the 'if ... and content' guard skips it."""
        msg = _tool_msg("get_portfolio_summary", "")
        result = _extract_tool_data([msg])
        assert "get_portfolio_summary" not in result

    def test_empty_message_list_returns_empty_dict(self):
        assert _extract_tool_data([]) == {}


class TestExtractToolDataWithFixtures:
    def test_mixed_message_list_returns_only_portfolio_summary(
        self, mixed_message_list
    ):
        """conftest.mixed_message_list has exactly one ToolMessage: get_portfolio_summary."""
        result = _extract_tool_data(mixed_message_list)
        assert set(result.keys()) == {"get_portfolio_summary"}

    def test_mixed_message_list_data_matches_sample_portfolio(
        self, mixed_message_list, sample_portfolio_data
    ):
        result = _extract_tool_data(mixed_message_list)
        assert result["get_portfolio_summary"] == sample_portfolio_data

    def test_mixed_message_list_result_has_correct_total_value(
        self, mixed_message_list
    ):
        result = _extract_tool_data(mixed_message_list)
        assert result["get_portfolio_summary"]["totalValue"] == 1_500_000
