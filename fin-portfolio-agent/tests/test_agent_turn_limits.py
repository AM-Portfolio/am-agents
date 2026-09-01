"""Token/cost guardrails — cap tool rounds per chat turn."""
from langchain_core.messages import AIMessage

from shared.agents.finance_agent import (
    AgentState,
    _build_cap_response,
    _tool_calls_exceeded,
)
from shared.agents.token_budget import reset_turn_token_budget
from shared.core.config import settings


def test_tool_calls_exceeded_at_limit():
    settings.AI_MAX_TOOL_CALLS_PER_TURN = 6
    assert _tool_calls_exceeded(["a"] * 6)
    assert not _tool_calls_exceeded(["a"] * 5)


def test_tool_calls_exceeded_zero_disables_cap():
    settings.AI_MAX_TOOL_CALLS_PER_TURN = 0
    assert not _tool_calls_exceeded(["a"] * 100)


def test_build_cap_response_uses_holdings_fallback():
    settings.AI_MAX_TOOL_CALLS_PER_TURN = 6
    state: AgentState = {
        "messages": [],
        "tools_called": ["get_holdings_list"],
        "final_response": None,
        "tool_data": {
            "get_holdings_list": {
                "holdings": [{"symbol": "RELIANCE"}],
                "count": 1,
            }
        },
    }
    out = _build_cap_response(state)
    assert "1 holdings" in out["final_response"]
    assert isinstance(out["messages"][0], AIMessage)


def test_build_cap_response_token_budget_message():
    from shared.agents.token_budget import record_turn_tokens

    settings.AI_MAX_TOOL_CALLS_PER_TURN = 6
    settings.AI_MAX_TOKENS_PER_TURN = 1000
    reset_turn_token_budget()
    record_turn_tokens({"total_tokens": 1000})
    state: AgentState = {
        "messages": [],
        "tools_called": ["get_stock_quote"],
        "final_response": None,
        "tool_data": {},
    }
    out = _build_cap_response(state)
    assert "too many tokens" in out["final_response"].lower()
