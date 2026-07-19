from __future__ import annotations

from app.models.intent import IntentDocument

_KEYWORDS = ["alert", "silence", "alertmanager"]


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = (query or "").lower()
    if not any(k in q for k in _KEYWORDS):
        return None
    operation = "silence.create"
    for candidate in ("silence.create", "silence.get", "silence.expire"):
        if candidate.replace(".", " ") in q or candidate in q:
            operation = candidate
            break
    op_read = {"silence.create": False, "silence.get": True, "silence.expire": False}
    return IntentDocument(
        backend=tool_name,
        operation=operation,
        params={},
        read_only=bool(op_read.get(operation, True)),
        confidence=0.7,
        rationale=f"rule match for {tool_name}",
    )
