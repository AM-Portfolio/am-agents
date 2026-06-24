import pytest

from app.intent_schema import IntentDocument
from app.registry import get_registry


def test_loki_registry_resolve():
    reg = get_registry()
    intent = IntentDocument(
        backend="loki",
        operation="query_logs",
        params={"query": '{job="am-analysis"}'},
        confidence=1.0,
        rationale="test",
    )
    call = reg.resolve(intent)
    assert call.operation == "query_logs"
    assert call.adapter_method == "query_logs"
    assert call.mcp_tool == "query_loki_logs" or call.source == "adapter"


def test_mongodb_count_registry():
    reg = get_registry()
    intent = IntentDocument(
        backend="mongodb",
        operation="count_documents",
        params={"database": "portfolio-db", "collection": "portfolios"},
        confidence=1.0,
        rationale="test",
    )
    call = reg.resolve(intent)
    assert call.operation == "count_documents"
