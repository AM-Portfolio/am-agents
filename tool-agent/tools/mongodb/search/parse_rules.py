from __future__ import annotations

import re
from typing import Any

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog
from tools._shared.extract import extract_uuid
from tools._shared.resolve import infer_entity_from_text

_DB_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"market[_\s-]?data", re.I), "market_data"),
    (re.compile(r"\bam-trade\b|am\s+trade", re.I), "am-trade"),
    (re.compile(r"trade[_\s-]?management", re.I), "trade_management"),
    (re.compile(r"mutual[_\s-]?funds?", re.I), "mutual_funds"),
    (re.compile(r"\bportfolio\b", re.I), "portfolio"),
    (re.compile(r"\bconfig\b", re.I), "config"),
    (re.compile(r"\banalysis\b", re.I), "analysis"),
]

_COLLECTION_HINTS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "portfolio": [
        (re.compile(r"\bsecurities\b", re.I), "securities"),
        (re.compile(r"\bportfolios?\b", re.I), "portfolios"),
    ],
    "market_data": [
        (re.compile(r"\binstruments?\b", re.I), "instruments"),
        (re.compile(r"\bsecurities\b", re.I), "securities"),
        (re.compile(r"\bingestion\b", re.I), "ingestion_job_logs"),
    ],
    "am-trade": [
        (re.compile(r"trade[_\s-]?details?", re.I), "trade_details"),
        (re.compile(r"portfolio[_\s-]?trades?", re.I), "portfolio_trades"),
        (re.compile(r"\btrades?\b", re.I), "trades"),
    ],
    "trade_management": [
        (re.compile(r"trade[_\s-]?details?", re.I), "trade_details"),
        (re.compile(r"portfolio[_\s-]?trades?", re.I), "portfolio_trades"),
        (re.compile(r"\btrades?\b", re.I), "trade"),
    ],
    "mutual_funds": [
        (re.compile(r"\betfs?\b", re.I), "etfs"),
        (re.compile(r"\bportfolios?\b", re.I), "portfolios"),
    ],
}


def _mongo_default_database() -> str:
    return get_schema_catalog().default_database("mongodb") or "portfolio"


def _infer_database(query: str) -> str:
    for pattern, database in _DB_HINTS:
        if pattern.search(query):
            return database
    return _mongo_default_database()


def _infer_collection(query: str, database: str) -> str:
    entity = infer_entity_from_text(query, backend="mongodb")
    if entity:
        mapping = get_schema_catalog().entity(entity)
        if mapping and mapping.backend == "mongodb" and mapping.collection:
            return mapping.collection
    for pattern, collection in _COLLECTION_HINTS.get(database, []):
        if pattern.search(query):
            return collection
    if database == "portfolio":
        return "portfolios"
    return "portfolios" if database == "mutual_funds" else "trades"


def _mongo_find_params(query: str) -> dict[str, Any]:
    db = _infer_database(query)
    coll = _infer_collection(query, db)
    filt: dict[str, Any] = {}
    entity = infer_entity_from_text(query, backend="mongodb")
    uuid = extract_uuid(query)
    if uuid and entity:
        mapping = get_schema_catalog().entity(entity)
        if mapping and mapping.backend == "mongodb":
            if mapping.database:
                db = mapping.database
            if mapping.collection:
                coll = mapping.collection
            filt[mapping.id_field] = uuid
        else:
            filt["_id"] = uuid
    elif uuid:
        filt["_id"] = uuid
    return {"database": db, "collection": coll, "filter": filt}


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    q = query.lower()
    if backend_hint != tool_name and "mongo" not in q:
        return None

    default_db = _mongo_default_database()
    if any(w in q for w in ("how many", "count", "number of", "no of", "no. of")):
        db = _infer_database(query)
        coll = _infer_collection(query, db)
        filt: dict[str, Any] = {}
        uuid = extract_uuid(query)
        if uuid:
            entity = infer_entity_from_text(query, backend="mongodb") or "portfolio"
            mapping = get_schema_catalog().entity(entity)
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
        db = _infer_database(query)
        return IntentDocument(
            backend="mongodb",
            operation="list_collections",
            params={"database": db},
            confidence=0.8,
            rationale="Rule: list mongo collections",
        )
    if "list database" in q or ("databases" in q and "mongo" in q):
        return IntentDocument(
            backend="mongodb",
            operation="list_databases",
            params={},
            confidence=0.8,
            rationale="Rule: list mongo databases",
        )
    if re.search(r"\bschema\b", q) and ("collection" in q or "portfolio" in q or "mongo" in q):
        db = _infer_database(query)
        coll = _infer_collection(query, db)
        return IntentDocument(
            backend="mongodb",
            operation="collection_schema",
            params={"database": db, "collection": coll, "sample_size": 20},
            confidence=0.8,
            rationale="Rule: mongo collection schema",
        )
    if "find" in q or "search" in q or extract_uuid(query):
        entity = infer_entity_from_text(query, backend="mongodb")
        uuid = extract_uuid(query)
        if entity and uuid:
            return IntentDocument(
                backend="mongodb",
                operation="find",
                params={"entity": entity, "id": uuid},
                confidence=0.9,
                rationale="Rule: mongo entity find by id",
            )
        return IntentDocument(
            backend="mongodb",
            operation="find",
            params=_mongo_find_params(query),
            confidence=0.75 if extract_uuid(query) else 0.7,
            rationale="Rule: mongo find",
        )
    if "list" in q and "databases" not in q and "collections" not in q and "list collection" not in q:
        return IntentDocument(
            backend="mongodb",
            operation="find",
            params=_mongo_find_params(query),
            confidence=0.7,
            rationale="Rule: mongo list sample",
        )
    return None
