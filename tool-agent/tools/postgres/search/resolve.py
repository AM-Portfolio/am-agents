from __future__ import annotations

from app.models.intent import IntentDocument
from tools._shared.resolve import resolve_intent_params


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    return resolve_intent_params(intent, query_text=query)
