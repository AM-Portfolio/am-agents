from __future__ import annotations

from app.models.intent import IntentDocument


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    _ = query
    return intent, None
