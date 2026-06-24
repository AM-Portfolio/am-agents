from __future__ import annotations

import re

_GOD_PREFIX_RE = re.compile(r"^\s*(?:god\s*mode|godmode|god)\s*[:>\-]\s*", re.I)
_GOD_INLINE_RE = re.compile(r"\b(?:god\s*mode|godmode)\b", re.I)


def strip_god_mode(query: str) -> tuple[str, bool]:
    text = query.strip()
    match = _GOD_PREFIX_RE.match(text)
    if match:
        return text[match.end() :].strip(), True
    if _GOD_INLINE_RE.search(text):
        cleaned = _GOD_INLINE_RE.sub("", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned, True
    return text, False
