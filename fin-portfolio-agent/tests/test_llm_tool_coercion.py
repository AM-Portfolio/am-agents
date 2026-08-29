import json

from shared.agents.llm_tool_coercion import coerce_llm_tool_response

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_summary",
            "description": "summary",
            "parameters": {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]},
        },
    }
]


def test_coerces_plain_text_function_call():
    out = coerce_llm_tool_response(
        "get_portfolio_summary()",
        _TOOLS,
        default_args={"userId": "u42"},
    )
    assert isinstance(out, dict)
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"
    assert json.loads(out["tool_calls"][0]["function"]["arguments"]) == {"userId": "u42"}


def test_leaves_normal_text_unchanged():
    text = "Here is your portfolio overview."
    assert coerce_llm_tool_response(text, _TOOLS) == text


def test_leaves_structured_tool_calls_unchanged():
    structured = {
        "content": "",
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_portfolio_summary", "arguments": "{}"}}],
    }
    assert coerce_llm_tool_response(structured, _TOOLS) is structured
