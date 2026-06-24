from __future__ import annotations

from typing import Any

from app.config import settings


def sanitize_payload(value: Any, *, max_chars: int | None = None) -> Any:
    limit = max_chars or settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    if isinstance(value, dict):
        return {k: sanitize_payload(v, max_chars=limit) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(v, max_chars=limit) for v in value[:50]]
    return value
