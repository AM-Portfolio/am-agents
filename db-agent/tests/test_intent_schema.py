from app.intent_schema import IntentDocument


def test_intent_document_valid():
    doc = IntentDocument(
        backend="qdrant",
        operation="list_collections",
        confidence=0.9,
        rationale="test",
    )
    assert doc.backend == "qdrant"
    assert doc.read_only is True
