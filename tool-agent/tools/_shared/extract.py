from __future__ import annotations

import re

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+", re.IGNORECASE)


def extract_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else None


def extract_uuid(text: str) -> str | None:
    match = UUID_PATTERN.search(text)
    return match.group(0) if match else None
