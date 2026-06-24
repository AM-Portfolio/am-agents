from __future__ import annotations

import re

from app.models.intent import IntentDocument


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = query.lower()
    if not (tool_name == "qdrant" or "qdrant" in q or "collection" in q and "vector" in q):
        return None

    if "search" in q:
        coll = None
        for token in re.findall(r"[\w_-]+", query):
            if token not in {"search", "qdrant", "in", "for", "collection"}:
                coll = token
                break
        return IntentDocument(
            backend=tool_name,
            operation="search",
            params={"collection": coll or "ui_patterns", "query": query},
            confidence=0.7,
            rationale="Rule: qdrant search",
        )

    if "count" in q or "points" in q or "info" in q:
        match = re.search(r"([\w_-]+)", query)
        coll = match.group(1) if match and "collection" not in match.group(1).lower() else None
        for token in re.findall(r"[\w_-]+", query):
            if token not in {"how", "many", "points", "in", "qdrant", "collection", "info"}:
                coll = token
                break
        if coll:
            return IntentDocument(
                backend=tool_name,
                operation="collection_info",
                params={"collection": coll},
                confidence=0.75,
                rationale="Rule: qdrant collection info",
            )

    return IntentDocument(
        backend=tool_name,
        operation="list_collections",
        params={},
        confidence=0.85,
        rationale="Rule: list qdrant collections",
    )
