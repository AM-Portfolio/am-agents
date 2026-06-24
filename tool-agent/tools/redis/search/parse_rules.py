from __future__ import annotations

import re

from app.models.intent import IntentDocument
from tools._shared.extract import extract_uuid


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = query.lower()
    if not (tool_name == "redis" or "redis" in q):
        return None

    uuid = extract_uuid(query)
    if uuid and ("session" in q or "get" in q or "key" in q):
        return IntentDocument(
            backend=tool_name,
            operation="get",
            params={"entity": "session", "id": uuid},
            confidence=0.8,
            rationale="Rule: redis session key lookup",
        )

    pattern = "*"
    if "session" in q:
        pattern = "session:*"
    elif "portfolio" in q:
        pattern = "portfolio:*"
    elif re.search(r"[\*\w:-]+", query):
        pattern = re.search(r"([\*\w:-]+)", query).group(1)  # type: ignore[union-attr]

    return IntentDocument(
        backend=tool_name,
        operation="scan_keys",
        params={"pattern": pattern},
        confidence=0.8,
        rationale="Rule: redis key scan",
    )
