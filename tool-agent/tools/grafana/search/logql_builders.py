from __future__ import annotations

import re

from tools._shared.extract import extract_uuid

_TRACE_LABEL_RE = re.compile(
    r"\b(?:trace[_\s-]?id|correlation[_\s-]?id|span[_\s-]?id)\s*[:=]?\s*"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.I,
)
_STATUS_RE = re.compile(r"\b(?:status|http)\s*[:=]?\s*(4\d\d|5\d\d)\b|\b(500|404|502|503)\b", re.I)
_PORTFOLIO_ID_RE = re.compile(
    r"\bportfolio[_\s-]?(?:id|uuid)\s*[:=]?\s*"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.I,
)


def extract_trace_id(text: str) -> str | None:
    match = _TRACE_LABEL_RE.search(text)
    if match:
        return match.group(1)
    if re.search(r"\b(?:trace|correlation|span)\b", text, re.I):
        return extract_uuid(text)
    return None


def extract_portfolio_id(text: str) -> str | None:
    match = _PORTFOLIO_ID_RE.search(text)
    if match:
        return match.group(1)
    if re.search(r"\bportfolio\b", text, re.I):
        return extract_uuid(text)
    return None


def extract_http_status(text: str) -> str | None:
    match = _STATUS_RE.search(text)
    if not match:
        return None
    return match.group(1) or match.group(2)


def logql_grep_id(selector: str, needle: str) -> str:
    return f'{selector} |= "{needle}"'


def logql_error_filter(selector: str) -> str:
    return f'{selector} |~ "(?i)(error|exception|failed)"'


def logql_status_filter(selector: str, status: str) -> str:
    return f'{selector} |~ "(?i)(\\"status\\"\\s*:\\s*{status}|status[_\\s-]?code\\"\\s*:\\s*{status}|\\b{status}\\b)"'


def logql_debug_bundle(selector: str, *, status: str | None = None) -> str:
    if status:
        return logql_status_filter(selector, status)
    return logql_error_filter(selector)
