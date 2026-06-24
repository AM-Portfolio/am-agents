from __future__ import annotations

import re
from typing import Any

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog
from tools._shared.extract import extract_email, extract_uuid
from tools._shared.resolve import infer_entity_from_text


def _mongo_default_database() -> str:
    return get_schema_catalog().default_database("mongodb") or "portfolio"


def _mongo_find_params(query: str) -> dict[str, Any]:
    db = _mongo_default_database()
    coll = "portfolios"
    filt: dict[str, Any] = {}
    entity = infer_entity_from_text(query, backend="mongodb")
    if entity:
        mapping = get_schema_catalog().entity(entity)
        if mapping and mapping.backend == "mongodb":
            if mapping.database:
                db = mapping.database
            if mapping.collection:
                coll = mapping.collection
    uuid = extract_uuid(query)
    if uuid:
        id_field = "_id"
        if entity:
            mapping = get_schema_catalog().entity(entity)
            if mapping:
                id_field = mapping.id_field
        filt[id_field] = uuid
    return {"database": db, "collection": coll, "filter": filt}


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    q = query.lower()
    if backend_hint != tool_name and "mongo" not in q:
        return None

    default_db = _mongo_default_database()
    email = extract_email(query)
    if email and re.search(r"\busers?\b", q):
        return IntentDocument(
            backend="mongodb",
            operation="find",
            params={
                "entity": "user",
                "lookup_field": "email",
                "lookup_value": email,
            },
            confidence=0.85,
            rationale="Rule: mongo user lookup by email",
        )
    if any(w in q for w in ("how many", "count", "number of", "no of", "no. of")):
        db = default_db
        coll = "portfolios"
        for token in re.findall(r"[\w_-]+", query):
            if token.lower() == "portfolios":
                coll = "portfolios"
            elif token.lower() == "users":
                coll = "users"
        filt: dict[str, Any] = {}
        uuid = extract_uuid(query)
        if uuid:
            mapping = get_schema_catalog().entity(infer_entity_from_text(query, backend="mongodb") or "portfolio")
            id_field = mapping.id_field if mapping else "_id"
            filt[id_field] = uuid
        return IntentDocument(
            backend="mongodb",
            operation="count_documents",
            params={"database": db, "collection": coll, "filter": filt},
            confidence=0.85,
            rationale="Rule: mongo document count",
        )
    if "list collection" in q or "collections" in q:
        db = default_db if "portfolio" in q else "admin"
        return IntentDocument(
            backend="mongodb",
            operation="list_collections",
            params={"database": db},
            confidence=0.8,
            rationale="Rule: list mongo collections",
        )
    if "find" in q or "search" in q or extract_uuid(query):
        return IntentDocument(
            backend="mongodb",
            operation="find",
            params=_mongo_find_params(query),
            confidence=0.75 if extract_uuid(query) else 0.7,
            rationale="Rule: mongo find",
        )
    return IntentDocument(
        backend="mongodb",
        operation="list_databases",
        params={},
        confidence=0.8,
        rationale="Rule: list mongo databases",
    )
