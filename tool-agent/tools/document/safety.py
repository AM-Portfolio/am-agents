from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError
from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation

WRITE_OPS = frozenset({
    "put",
})


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    risk = risk_for_operation(intent.operation)
    is_write = intent.operation in WRITE_OPS or requires_write_confirmation(risk)
    if request_read_only and is_write:
        raise SafetyError(f"{intent.backend}.{intent.operation} blocked in read-only mode")
    if is_write and not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError(f"{intent.backend} writes blocked: TOOL_AGENT_ALLOW_WRITES=false")


def validate_tool_params(operation: str, params: dict) -> None:
    _ = params
    if operation not in {'put', 'get', 'exists', 'signed-url.create'}:
        raise ValueError(f"unknown operation {operation!r}")
