from __future__ import annotations

import re

from app.models.intent import IntentDocument

_COLLECTION_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"bug[_\s-]?memory|past\s+bugs?", re.I), "bug_memory"),
    (re.compile(r"test[_\s-]?cases?", re.I), "test_cases"),
    (re.compile(r"ui[_\s-]?patterns?", re.I), "ui_patterns"),
]


def _collection_from_query(query: str) -> str | None:
    for pattern, coll in _COLLECTION_ALIASES:
        if pattern.search(query):
            return coll
    match = re.search(r"collection\s+([\w_-]+)", query, re.I)
    if match:
        return match.group(1)
    return None


def parse_rules(query: str, *, tool_name: str, backend_hint: str | None = None) -> IntentDocument | None:
    q = query.lower()
    if not (tool_name == "qdrant" or backend_hint == "qdrant" or "qdrant" in q or "vector" in q):
        if not (_collection_from_query(query) and ("search" in q or "similar" in q)):
            return None

    coll = _collection_from_query(query)

    if re.search(r"\bsearch\b|\bsimilar\b|\bfind\b.*\blike\b", q):
        return IntentDocument(
            backend=tool_name,
            operation="search",
            params={"collection": coll or "bug_memory", "query": query},
            confidence=0.82,
            rationale="Rule: qdrant semantic search",
        )

    if re.search(r"\bscroll\b|\blist\s+points\b|\bsample\b", q):
        return IntentDocument(
            backend=tool_name,
            operation="scroll",
            params={"collection": coll or "bug_memory", "limit": 10},
            confidence=0.78,
            rationale="Rule: qdrant scroll sample",
        )

    if "count" in q or "points" in q or "info" in q or coll:
        return IntentDocument(
            backend=tool_name,
            operation="collection_info",
            params={"collection": coll or "bug_memory"},
            confidence=0.8,
            rationale="Rule: qdrant collection info",
        )

    return IntentDocument(
        backend=tool_name,
        operation="list_collections",
        params={},
        confidence=0.88,
        rationale="Rule: list qdrant collections",
    )
