from app.observability.trace_labels import (
    execute_tool_span_name,
    source_label,
    validate_safety_span_name,
)
from app.intent_schema import IntentDocument, ToolCall


def test_source_label_native_adapter():
    tool = ToolCall(
        backend="qdrant",
        operation="collection_info",
        params={"collection": "ui_patterns"},
        source="adapter",
        adapter_method="collection_info",
    )
    assert source_label(tool) == "native-adapter/qdrant"
    assert execute_tool_span_name(tool) == (
        "execute tool · qdrant.collection_info via native-adapter/qdrant"
    )


def test_trace_name_and_tags():
    from app.observability.trace_labels import trace_name, trace_tags

    assert trace_name("qdrant", "list_collections") == "db-agent · qdrant · list_collections"
    assert trace_name("mongodb", None, pending=True) == "db-agent · mongodb · …"
    assert trace_name(None, None) == "db-agent · query"
    assert trace_tags("redis", "info", parse_source="rules") == [
        "db-agent",
        "backend:redis",
        "op:info",
        "parse:rules",
    ]


def test_validate_safety_span_name():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={"sql": "SELECT 1"},
        confidence=0.9,
        rationale="test",
    )
    assert validate_safety_span_name(intent) == "validate safety · postgres.run_sql"
