from __future__ import annotations

import json
import re
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|token|api_key|apikey|secret|authorization|credential)",
    re.IGNORECASE,
)
URL_CREDENTIAL_PATTERN = re.compile(
    r"://([^:/@]+):([^@]+)@",
    re.IGNORECASE,
)


def redact_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {k: redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(key, v) for v in value[:10]]
    if isinstance(value, str):
        if SECRET_KEY_PATTERN.search(key):
            return "***"
        return URL_CREDENTIAL_PATTERN.sub("://***:***@", value)
    return value


def truncate_for_trace(data: Any, max_chars: int) -> Any:
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        text = json.dumps(data, default=str)
        if len(text) <= max_chars:
            return data
        return {"_truncated": True, "preview": text[:max_chars]}
    text = str(data)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(truncated)"


def sanitize_payload(data: Any, *, max_chars: int = 8000) -> Any:
    redacted = redact_value("", data)
    return truncate_for_trace(redacted, max_chars)
