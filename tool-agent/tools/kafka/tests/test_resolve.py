from tools.kafka.search.resolve import resolve
from app.models.intent import IntentDocument


def test_resolve_passthrough():
    intent = IntentDocument(
        backend="kafka",
        operation="list_topics",
        params={},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "kafka topics")
    assert resolved.operation == "list_topics"
    assert entity is None
