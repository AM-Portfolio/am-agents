from __future__ import annotations

from app.models.intent import IntentDocument


def resolve(intent: IntentDocument, raw_query: str) -> tuple[IntentDocument, str | None]:
    return intent, None
