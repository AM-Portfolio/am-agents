from app.intent_schema import IntentDocument
from app.registry import ToolRegistry


def test_resolve_qdrant_to_adapter_when_mcp_disabled():
    reg = ToolRegistry()
    intent = IntentDocument(
        backend="qdrant",
        operation="list_collections",
        confidence=0.9,
        rationale="test",
    )
    call = reg.resolve(intent)
    assert call.source == "adapter"
    assert call.adapter_method == "list_collections"
