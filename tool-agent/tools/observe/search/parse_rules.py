from __future__ import annotations

from app.models.intent import IntentDocument

_KEYWORDS = ['observe', 'metrics', 'logs', 'timeseries', 'grafana']


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = (query or "").lower()
    if not any(k in q for k in _KEYWORDS):
        return None
    operation = "get"
    read_only = True
    for candidate in ('metrics.query', 'logs.query', 'timeseries.query'):
        if candidate.replace(".", " ") in q or candidate in q:
            operation = candidate
            break
    op_read = {'metrics.query': True, 'logs.query': True, 'timeseries.query': True}
    read_only = bool(op_read.get(operation, True))
    return IntentDocument(
        backend=tool_name,
        operation=operation,
        params={},
        read_only=read_only,
        confidence=0.7,
        rationale=f"rule match for {tool_name}",
    )
