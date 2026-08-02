from __future__ import annotations

from typing import Any

from shared.core.config import settings


def sanitize_payload(value: Any, *, max_chars: int | None = None) -> Any:
    """Truncate nested payloads for Langfuse; never raise."""
    limit = max_chars if max_chars is not None else settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS
    try:
        if isinstance(value, str):
            return value if len(value) <= limit else value[:limit] + "…"
        if isinstance(value, dict):
            return {str(k): sanitize_payload(v, max_chars=limit) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_payload(v, max_chars=limit) for v in value[:50]]
        return value
    except Exception:  # noqa: BLE001
        return {"_sanitize_error": True}
