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
            confidence=0.9,
            rationale="Rule: postgres user lookup by email",
        )

    if email and "portfolio" in q:
        return IntentDocument(
            backend="postgres",
            operation="run_sql",
            params={
                "entity": "portfolio_pg",
                "lookup_field": "email",
                "lookup_value": email,
            },
            confidence=0.8,
            rationale="Rule: postgres portfolio lookup by owner email",
        )

    if uuid:
        if "subscription" in q:
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={"entity": "subscription", "id": uuid},
                confidence=0.85,
                rationale="Rule: postgres subscription by id",
            )
        if re.search(r"\bsecurit", q):
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={"entity": "portfolio_security_pg", "id": uuid},
                confidence=0.85,
                rationale="Rule: postgres security by id",
            )
        if "session" in q and "redis" not in q:
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={"entity": "session_pg", "id": uuid},
                confidence=0.8,
                rationale="Rule: postgres session row by id",
            )
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
        entity = None
        if "portfolio" in q and "securit" not in q:
            entity = "portfolio_pg"
        elif "user" in q:
            entity = "user_account"
        elif "subscription" in q:
            entity = "subscription"
        elif re.search(r"\bsecurit", q):
            entity = "portfolio_security_pg"
        params: dict[str, str] = {}
        if entity:
            params["entity"] = entity
        else:
            params["pattern"] = "portfolio"
        return IntentDocument(
            backend="postgres",
            operation="table_row_count" if entity else "search_schema",
            params=params,
            confidence=0.78,
            rationale="Rule: postgres count or schema search",
        )

    if "schema" in q or "tables" in q or "search" in q:
        pattern = "%"
        if "user" in q:
            pattern = "user"
        elif "portfolio" in q:
            pattern = "portfolio"
        elif "subscription" in q:
            pattern = "subscription"
        elif "session" in q:
            pattern = "session"
        return IntentDocument(
            backend="postgres",
            operation="search_schema",
            params={"pattern": pattern},
            confidence=0.75,
            rationale="Rule: postgres schema search",
        )

    return IntentDocument(
        backend="postgres",
        operation="search_schema",
        params={"pattern": "user_accounts" if "user" in q else "portfolio" if "portfolio" in q else "%"},
        confidence=0.7,
        rationale="Rule: postgres schema search fallback",
    )
