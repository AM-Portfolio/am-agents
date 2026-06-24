from __future__ import annotations

from app.models.intent import IntentDocument, SafetyError


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and intent.read_only is False:
        raise SafetyError("Writes are not supported for this tool template")
