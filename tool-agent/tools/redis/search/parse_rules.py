from __future__ import annotations

import re

from app.models.intent import IntentDocument
from tools._shared.extract import extract_uuid


def parse_rules(query: str, *, tool_name: str, backend_hint: str | None = None) -> IntentDocument | None:
    q = query.lower()
    if backend_hint != tool_name and "redis" not in q:
        return None

    if re.search(r"\binfo\b", q) and "redis" in q:
        return IntentDocument(
            backend=tool_name,
            operation="info",
            params={},
            confidence=0.9,
            rationale="Rule: redis server info",
        )

    uuid = extract_uuid(query)
    if uuid and ("session" in q or "get" in q or "key" in q):
        return IntentDocument(
            backend=tool_name,
            operation="get",
            params={"entity": "session", "id": uuid},
            confidence=0.88,
            rationale="Rule: redis session key lookup",
        )

    if uuid and "portfolio" in q:
        return IntentDocument(
            backend=tool_name,
            operation="get",
            params={"entity": "portfolio_cache", "id": uuid},
            confidence=0.85,
            rationale="Rule: redis portfolio cache lookup",
        )

    if uuid and "user" in q:
        return IntentDocument(
            backend=tool_name,
            operation="get",
            params={"entity": "user_cache", "id": uuid},
            confidence=0.85,
            rationale="Rule: redis user cache lookup",
        )

    if "type" in q and re.search(r"key\s+([\w:*-]+)", q):
        key_match = re.search(r"key\s+([\w:*-]+)", q)
        return IntentDocument(
            backend=tool_name,
            operation="type",
            params={"key": key_match.group(1) if key_match else "*"},
            confidence=0.8,
            rationale="Rule: redis key type",
        )

    pattern = "*"
    if "session" in q:
        pattern = "session:*"
    elif "portfolio" in q:
        pattern = "portfolio:*"
    elif "user" in q and "session" not in q:
        pattern = "user:*"
    elif "ratelimit" in q or "rate limit" in q:
        pattern = "ratelimit:*"
    elif re.search(r"[\*\w:-]+", query):
        match = re.search(r"([\*\w:-]+)", query)
        if match and match.group(1) not in {"redis", "keys", "scan", "list"}:
            pattern = match.group(1)

    return IntentDocument(
        backend=tool_name,
        operation="scan_keys",
        params={"pattern": pattern},
        confidence=0.8,
        rationale="Rule: redis key scan",
    )
