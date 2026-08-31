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


def test_coerces_xml_tool_call_block():
    xml = """<tool_call>
<function=get_portfolio_summary>
</function>
</tool_call>"""
    out = coerce_llm_tool_response(
        xml,
        _TOOLS,
        default_args={"userId": "u42"},
    )
    assert isinstance(out, dict)
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"
    assert json.loads(out["tool_calls"][0]["function"]["arguments"]) == {"userId": "u42"}


def test_coerces_json_inside_tool_call_block():
    payload = (
        '<tool_call>{"name": "get_portfolio_summary", '
        '"arguments": {"userId": "u99"}}</tool_call>'
    )
    out = coerce_llm_tool_response(payload, _TOOLS)
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"
    assert json.loads(out["tool_calls"][0]["function"]["arguments"]) == {"userId": "u99"}


def test_coerces_markdown_json_fence():
    text = 'Here is the call:\n```json\n{"tool": "get_portfolio_summary"}\n```'
    out = coerce_llm_tool_response(
        text,
        _TOOLS,
        default_args={"userId": "u42"},
    )
    assert isinstance(out, dict)
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"


def test_coerces_inline_json_tool_key():
    text = 'I will call {"tool": "get_portfolio_summary", "arguments": {}} now.'
    out = coerce_llm_tool_response(text, _TOOLS, default_args={"userId": "u1"})
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"


def test_xml_tool_call_uses_full_registry_when_not_in_retrieved_tools(monkeypatch):
    xml = """<tool_call>
<function=get_portfolio_summary>
</function>
</tool_call>"""
    monkeypatch.setattr(
        "shared.tools.registry.TOOL_REGISTRY",
        _TOOLS,
    )
    out = coerce_llm_tool_response(xml, [], default_args={"userId": "u1"})
    assert isinstance(out, dict)
    assert out["tool_calls"][0]["function"]["name"] == "get_portfolio_summary"
