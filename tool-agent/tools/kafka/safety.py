from __future__ import annotations

from app.models.intent import IntentDocument, SafetyError

KAFKA_WRITE_OPS = frozenset({"produce", "publish"})


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and intent.read_only is False:
        raise SafetyError("Writes are not supported for kafka")
    if request_read_only and intent.operation in KAFKA_WRITE_OPS:
        raise SafetyError(f"Kafka operation '{intent.operation}' is blocked in read-only mode")


def validate_tool_params(operation: str, params: dict) -> None:
    if operation in {"describe_topic", "peek_messages"} and not params.get("topic"):
        raise ValueError(f"topic required for kafka.{operation}")
