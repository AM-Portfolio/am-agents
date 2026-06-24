from __future__ import annotations

import re

from app.models.intent import IntentDocument
from tools._shared.extract import extract_email, extract_uuid


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    q = query.lower()
    if backend_hint != tool_name and "postgres" not in q and "sql" not in q:
        return None

    uuid = extract_uuid(query)
    email = extract_email(query)
    if email and re.search(r"\busers?\b", q):
        return IntentDocument(
            backend="postgres",
            operation="run_sql",
            params={
                "entity": "user_account",
                "lookup_field": "email",
                "lookup_value": email,
            },
            confidence=0.85,
            rationale="Rule: postgres user lookup by email",
        )
    if email and re.search(r"\busers?\b", q) is None and "portfolio" in q:
        return IntentDocument(
            backend="postgres",
            operation="run_sql",
            params={
                "entity": "portfolio_pg",
                "lookup_field": "email",
                "lookup_value": email,
            },
            confidence=0.75,
            rationale="Rule: postgres lookup by email",
        )
    if uuid and ("portfolio" in q or "user" in q or "find" in q or "get" in q):
        entity = (
            "portfolio_pg"
            if "portfolio" in q
            else "user_account"
            if "user" in q
            else "portfolio_pg"
        )
        return IntentDocument(
            backend="postgres",
            operation="run_sql",
            params={"entity": entity, "id": uuid},
            confidence=0.8,
            rationale="Rule: postgres row lookup by entity",
        )
    if any(w in q for w in ("how many", "count", "number of", "row count")):
        entity = (
            "portfolio_pg"
            if "portfolio" in q
            else "user_account"
            if "user" in q
            else None
        )
        params: dict[str, str] = {}
        if entity:
            params["entity"] = entity
        else:
            params["pattern"] = "portfolio"
        return IntentDocument(
            backend="postgres",
            operation="table_row_count" if entity else "search_schema",
            params=params,
            confidence=0.75,
            rationale="Rule: postgres count or schema search",
        )
    return IntentDocument(
        backend="postgres",
        operation="search_schema",
        params={"pattern": "user_accounts" if "user" in q else "portfolio" if "portfolio" in q else "%"},
        confidence=0.7,
        rationale="Rule: postgres schema search",
    )
