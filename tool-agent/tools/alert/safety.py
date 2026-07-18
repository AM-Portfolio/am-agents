from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError
from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation

WRITE_OPS = frozenset({"silence.create", "silence.expire"})


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    risk = risk_for_operation(intent.operation)
    is_write = intent.operation in WRITE_OPS or requires_write_confirmation(risk)
    if request_read_only and is_write:
        raise SafetyError(f"{intent.backend}.{intent.operation} blocked in read-only mode")
    if is_write and not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError(f"{intent.backend} writes blocked: TOOL_AGENT_ALLOW_WRITES=false")


def validate_tool_params(operation: str, params: dict) -> None:
    if operation not in {"silence.create", "silence.get", "silence.expire"}:
        raise ValueError(f"unknown operation {operation!r}")
    if operation == "silence.create":
        env = str(params.get("env") or "").strip()
        service = str(params.get("service") or "").strip()
        minutes = int(params.get("minutes") or 0)
        if not env or not service:
            raise ValueError("env and service are required (refusing global silence)")
        if minutes < 5 or minutes > 60 * 24 * 14:
            raise ValueError("duration must be between 5 minutes and 14 days")
    if operation in {"silence.get", "silence.expire"} and not str(params.get("silence_id") or "").strip():
        raise ValueError("silence_id required")
