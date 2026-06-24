from __future__ import annotations

from app.models.intent import IntentDocument


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = query.lower().strip()
    if f"{tool_name} ping" in q or q == "ping":
        return IntentDocument(
            backend=tool_name,
            operation="ping",
            params={},
            read_only=True,
            confidence=0.9,
            rationale="rule: ping",
        )
    return None
