from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.models.intent import IntentDocument, SafetyError

MONGO_WRITE_KEYS = frozenset(
    {"deleteMany", "deleteOne", "insert", "insertOne", "update", "updateMany", "drop", "$out", "$merge"}
)
WRITE_OPERATIONS = frozenset({"aggregate"})


def _validate_mongo_params(params: dict[str, Any]) -> None:
    blob = json.dumps(params, default=str).lower()
    for key in MONGO_WRITE_KEYS:
        if key.lower() in blob:
            raise SafetyError(f"Mongo write operation '{key}' is blocked in read-only mode")


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError("Writes are disabled (TOOL_AGENT_ALLOW_WRITES=false)")

    if intent.operation in WRITE_OPERATIONS:
        raise SafetyError(f"MongoDB operation '{intent.operation}' is blocked (writes not supported)")

    if request_read_only or settings.TOOL_AGENT_READ_ONLY_DEFAULT:
        if not intent.read_only:
            raise SafetyError("Intent marked read_only=false but request requires read-only")
        _validate_mongo_params(intent.params)


def validate_tool_params(operation: str, params: dict[str, Any]) -> None:
    if operation in WRITE_OPERATIONS:
        raise SafetyError(f"MongoDB operation '{operation}' is blocked (writes not supported)")
    _validate_mongo_params(params)
