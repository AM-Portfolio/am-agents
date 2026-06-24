from tools._template.search.resolve import resolve
from app.models.intent import IntentDocument


def test_resolve_passthrough():
    intent = IntentDocument(
        backend="example",
        operation="ping",
        params={},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "ping")
    assert resolved.operation == "ping"
    assert entity is None
