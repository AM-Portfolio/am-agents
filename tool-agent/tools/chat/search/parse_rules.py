from __future__ import annotations

from app.models.intent import IntentDocument

_KEYWORDS = ['chat', 'cliq', 'notify', 'message']


def parse_rules(query: str, *, tool_name: str, backend_hint: str | None = None) -> IntentDocument | None:
    q = (query or "").lower()
    if not any(k in q for k in _KEYWORDS):
        return None
    operation = "message.send"
    read_only = True
    for candidate in ('message.send', 'card.send'):
        if candidate.replace(".", " ") in q or candidate in q:
            operation = candidate
            break
    op_read = {'message.send': False, 'card.send': False}
    read_only = bool(op_read.get(operation, True))
    return IntentDocument(
        backend=tool_name,
        operation=operation,
        params={},
        read_only=read_only,
        confidence=0.7,
        rationale=f"rule match for {tool_name}",
    )
