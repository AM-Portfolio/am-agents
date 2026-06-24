from __future__ import annotations

from app.models.intent import IntentDocument, SafetyError

QDRANT_WRITE_OPS = frozenset({"upsert", "delete", "create_collection", "delete_collection"})


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and intent.read_only is False:
        raise SafetyError("Writes are not supported for qdrant")
    if request_read_only and intent.operation in QDRANT_WRITE_OPS:
        raise SafetyError(f"Qdrant operation '{intent.operation}' is blocked in read-only mode")
