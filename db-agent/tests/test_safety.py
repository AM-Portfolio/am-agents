import pytest

from app.intent_schema import IntentDocument, SafetyError, ToolCall
from app.safety import cap_rows, validate_intent, validate_tool_call


def test_blocks_sql_writes():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={"sql": "DELETE FROM users"},
        confidence=0.9,
        rationale="test",
    )
    with pytest.raises(SafetyError):
        validate_intent(intent, request_read_only=True)


def test_allows_select():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={"sql": "SELECT 1"},
        confidence=0.9,
        rationale="test",
    )
    validate_intent(intent, request_read_only=True)


def test_blocks_copy_and_merge():
    for sql in ("COPY users TO '/tmp/x'", "MERGE INTO t USING s ON 1=1"):
        intent = IntentDocument(
            backend="postgres",
            operation="run_sql",
            params={"sql": sql},
            confidence=0.9,
            rationale="test",
        )
        with pytest.raises(SafetyError):
            validate_intent(intent, request_read_only=True)


def test_blocks_mongo_write_in_aggregate():
    intent = IntentDocument(
        backend="mongodb",
        operation="aggregate",
        params={"pipeline": [{"$out": "other"}]},
        confidence=0.9,
        rationale="test",
    )
    with pytest.raises(SafetyError):
        validate_intent(intent, request_read_only=True)


def test_blocks_redis_flush():
    intent = IntentDocument(
        backend="redis",
        operation="get",
        params={"command": "FLUSHALL"},
        confidence=0.9,
        rationale="test",
    )
    with pytest.raises(SafetyError):
        validate_intent(intent, request_read_only=True)


def test_validate_tool_call_blocks_nested_sql():
    tool_call = ToolCall(
        backend="postgres",
        operation="run_sql",
        params={"sql": "DROP TABLE users"},
        source="adapter",
        read_only=True,
    )
    with pytest.raises(SafetyError):
        validate_tool_call(tool_call)


def test_validate_tool_call_blocks_non_readonly_mcp():
    tool_call = ToolCall(
        backend="postgres",
        operation="run_sql",
        params={"sql": "SELECT 1"},
        source="mcp",
        read_only=False,
    )
    with pytest.raises(SafetyError):
        validate_tool_call(tool_call)


def test_cap_rows_truncates():
    data, warnings = cap_rows(list(range(200)), 100)
    assert len(data) == 100
    assert warnings
