from shared.agents.llm_tool_coercion import coerce_llm_tool_response, describe_coercion
from shared.observability.langfuse_tracer import (
    _apply_prompt_link,
    _omit_none,
    serialize_chat_messages,
    serialize_llm_output,
)

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


def test_serialize_chat_messages_includes_system_prompt():
    rows, meta = serialize_chat_messages(
        [
            {"role": "system", "content": "You are a finance agent."},
            {"role": "user", "content": "Show portfolio"},
        ],
        tools=_TOOLS,
    )
    assert rows[0]["role"] == "system"
    assert "finance agent" in rows[0]["content"]
    assert meta["tool_names"] == ["get_portfolio_summary"]


def test_serialize_llm_output_with_tool_calls():
    out = serialize_llm_output(
        {"content": "", "tool_calls": [{"function": {"name": "get_portfolio_summary"}}]}
    )
    assert "tool_calls" in out


def test_describe_coercion_detects_plain_text():
    before = "get_portfolio_summary()"
    after = coerce_llm_tool_response(before, _TOOLS, default_args={"userId": "u1"})
    meta = describe_coercion(before, after)
    assert meta is not None
    assert meta["coerced"] is True
    assert meta["raw_text"] == "get_portfolio_summary()"


def test_apply_prompt_link_requires_version_pair(monkeypatch):
    monkeypatch.setattr(
        "shared.observability.langfuse_tracer.settings.LANGFUSE_PROMPT_VERSION",
        "",
    )
    body: dict = {}
    _apply_prompt_link(body)
    assert "promptName" not in body
    assert "promptVersion" not in body

    monkeypatch.setattr(
        "shared.observability.langfuse_tracer.settings.LANGFUSE_PROMPT_VERSION",
        "3",
    )
    monkeypatch.setattr(
        "shared.observability.langfuse_tracer.settings.LANGFUSE_PROMPT_NAME",
        "fin-agent/finance-system",
    )
    body = {}
    _apply_prompt_link(body)
    assert body["promptName"] == "fin-agent/finance-system"
    assert body["promptVersion"] == 3


def test_omit_none_strips_null_metadata():
    assert _omit_none({"a": 1, "b": None, "c": "ok"}) == {"a": 1, "c": "ok"}
