"""Redact secrets/PII and bound attribute payloads for agent-work events."""

from __future__ import annotations

from typing import Any

_FORBIDDEN_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "private_key",
    "credential",
)
_MAX_DEPTH = 4
_MAX_LIST = 20
_MAX_STR = 512
_MAX_KEYS = 40


def _forbidden(key: str) -> bool:
    lowered = key.lower()
    return any(frag in lowered for frag in _FORBIDDEN_KEY_FRAGMENTS)


def sanitize_attributes(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_STR else value[:_MAX_STR] + "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= _MAX_KEYS:
                out["_truncated_keys"] = True
                break
            key = str(k)
            if _forbidden(key):
                out[key] = "***"
            else:
                out[key] = sanitize_attributes(v, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        items = list(value)[:_MAX_LIST]
        return [sanitize_attributes(v, depth=depth + 1) for v in items]
    return str(value)[:_MAX_STR]
