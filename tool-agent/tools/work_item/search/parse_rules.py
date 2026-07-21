from __future__ import annotations

from app.models.intent import IntentDocument

_KEYWORDS = ['work-item', 'work item', 'ticket', 'openproject', 'workpackage']


def parse_rules(query: str, *, tool_name: str, backend_hint: str | None = None) -> IntentDocument | None:
    q = (query or "").lower()
    if backend_hint and backend_hint != tool_name:
        return None
    if not backend_hint == tool_name and not any(k in q for k in _KEYWORDS):
        return None

    # Check for explicit keywords
    operation = "search"
    matched = False
    for candidate in ('search', 'get', 'create', 'comment', 'assign', 'transition'):
        if candidate in q:
            operation = candidate
            matched = True
            break

    if not matched:
        # Fallback if no explicit operation keyword:
        # If there's a reference to a specific ticket number/ID or view words, assume "get"
        import re
        if re.search(r'\b\d+\b|op:wp:', q) or any(w in q for w in ("get", "show", "view", "ticket")):
            operation = "get"
        else:
            operation = "search"

    op_read = {'search': True, 'get': True, 'create': False, 'comment': False, 'assign': False, 'transition': False}
    read_only = bool(op_read.get(operation, True))
    return IntentDocument(
        backend=tool_name,
        operation=operation,
        params={},
        read_only=read_only,
        confidence=0.7,
        rationale=f"rule match for {tool_name}",
    )
