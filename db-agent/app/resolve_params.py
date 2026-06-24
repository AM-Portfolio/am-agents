from __future__ import annotations

import copy
import re
from typing import Any

from app.intent_schema import BACKEND_OPERATIONS, IntentDocument
from app.schema_catalog import (
    EntityMapping,
    get_schema_catalog,
    postgres_select_by_field,
    postgres_select_sql,
)

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+", re.IGNORECASE)

MONGO_DB_COLL_OPS = frozenset(
    {"find", "aggregate", "count_documents", "collection_schema", "list_collections"}
)
QDRANT_COLL_OPS = frozenset({"collection_info", "scroll", "search"})
POSTGRES_TABLE_OPS = frozenset({"run_sql", "table_row_count", "search_schema"})
REDIS_KEY_OPS = frozenset({"get", "type", "scan_keys"})

_ENTITY_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsessions?\b"), "session"),
    (re.compile(r"\busers?\b"), "user"),
    (re.compile(r"\bportfolios?\b"), "portfolio"),
    (re.compile(r"bug_memory|bug memory", re.I), "bug_memory"),
]


class ParamResolutionError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def extract_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else None


def extract_uuid(text: str) -> str | None:
    match = UUID_PATTERN.search(text)
    return match.group(0) if match else None


def _resolve_lookup_column(mapping: EntityMapping, lookup_field: str) -> str:
    return mapping.lookup_fields.get(lookup_field, lookup_field)


def _apply_lookup(
    mapping: EntityMapping,
    resolved: dict[str, Any],
    *,
    lookup_field: str,
    lookup_value: str,
) -> dict[str, Any]:
    column = _resolve_lookup_column(mapping, lookup_field)
    if mapping.backend == "mongodb":
        filt = dict(resolved.get("filter") or {})
        filt[column] = lookup_value
        resolved["filter"] = filt
    elif mapping.backend == "postgres" and not resolved.get("sql"):
        resolved["sql"] = postgres_select_by_field(mapping, column, lookup_value)
    return resolved


def infer_entity_from_text(text: str, *, backend: str | None = None) -> str | None:
    q = text.lower()
    for pattern, entity in _ENTITY_HINTS:
        if pattern.search(q):
            if backend == "postgres" and entity == "user":
                return "user_account"
            if backend == "postgres" and entity == "portfolio":
                return "portfolio_pg"
            if backend == "redis" and entity == "portfolio":
                return "portfolio_cache"
            return entity
    return None


def _apply_entity_mapping(
    params: dict[str, Any],
    mapping: EntityMapping,
    *,
    entity_id: str | None,
    lookup_field: str | None = None,
    lookup_value: str | None = None,
) -> dict[str, Any]:
    resolved = dict(params)
    resolved.pop("entity", None)
    if entity_id is not None:
        resolved.pop("id", None)
    if lookup_field is not None:
        resolved.pop("lookup_field", None)
    if lookup_value is not None:
        resolved.pop("lookup_value", None)

    if mapping.backend == "mongodb":
        if not resolved.get("database") and mapping.database:
            resolved["database"] = mapping.database
        if not resolved.get("collection") and mapping.collection:
            resolved["collection"] = mapping.collection
        if lookup_field and lookup_value:
            resolved = _apply_lookup(
                mapping, resolved, lookup_field=lookup_field, lookup_value=lookup_value
            )
        elif entity_id:
            filt = dict(resolved.get("filter") or {})
            filt.setdefault(mapping.id_field, entity_id)
            resolved["filter"] = filt

    elif mapping.backend == "postgres":
        if not resolved.get("schema") and mapping.schema:
            resolved["schema"] = mapping.schema
        if not resolved.get("table") and mapping.table:
            resolved["table"] = mapping.table
        if lookup_field and lookup_value and not resolved.get("sql"):
            resolved = _apply_lookup(
                mapping, resolved, lookup_field=lookup_field, lookup_value=lookup_value
            )
        elif entity_id and not resolved.get("sql"):
            resolved["sql"] = postgres_select_sql(mapping, entity_id)
        elif mapping.table and not resolved.get("pattern"):
            resolved["pattern"] = mapping.table

    elif mapping.backend == "redis":
        if entity_id and mapping.key_template:
            resolved["key"] = mapping.key_template.format(id=entity_id)
        elif not resolved.get("pattern") and mapping.key_pattern:
            resolved["pattern"] = mapping.key_pattern

    elif mapping.backend == "qdrant":
        if not resolved.get("collection") and mapping.collection:
            resolved["collection"] = mapping.collection

    return resolved


def _maybe_upgrade_redis_operation(intent: IntentDocument, params: dict[str, Any]) -> IntentDocument:
    if intent.backend != "redis" or intent.operation != "scan_keys":
        return intent
    if params.get("key"):
        return intent.model_copy(update={"operation": "get"})
    return intent


def resolve_intent_params(
    intent: IntentDocument,
    *,
    query_text: str = "",
) -> tuple[IntentDocument, str | None]:
    """Expand entity-centric or partial params using schema catalog."""
    catalog = get_schema_catalog()
    params = copy.deepcopy(intent.params)
    entity_name: str | None = params.pop("entity", None) or None
    entity_id: str | None = params.pop("id", None) or None
    lookup_field: str | None = params.pop("lookup_field", None) or None
    lookup_value: str | None = params.pop("lookup_value", None) or None

    if entity_name:
        mapping = catalog.entity(entity_name)
        if not mapping:
            raise ParamResolutionError(f"Unknown entity '{entity_name}' in schema catalog")
        if mapping.backend != intent.backend:
            raise ParamResolutionError(
                f"Entity '{entity_name}' maps to backend '{mapping.backend}', "
                f"not '{intent.backend}'"
            )
        params = _apply_entity_mapping(
            params,
            mapping,
            entity_id=entity_id,
            lookup_field=lookup_field,
            lookup_value=lookup_value,
        )
    elif lookup_field and lookup_value:
        inferred = infer_entity_from_text(query_text, backend=intent.backend)
        if inferred:
            mapping = catalog.entity(inferred)
            if mapping and mapping.backend == intent.backend:
                entity_name = inferred
                params = _apply_entity_mapping(
                    params,
                    mapping,
                    entity_id=entity_id,
                    lookup_field=lookup_field,
                    lookup_value=lookup_value,
                )
    elif entity_id:
        inferred = infer_entity_from_text(query_text, backend=intent.backend)
        if inferred:
            mapping = catalog.entity(inferred)
            if mapping and mapping.backend == intent.backend:
                entity_name = inferred
                params = _apply_entity_mapping(params, mapping, entity_id=entity_id)

    if intent.backend == "mongodb":
        if not params.get("database"):
            default_db = catalog.default_database("mongodb")
            if default_db:
                params["database"] = default_db

        if intent.operation in ("find", "count_documents", "aggregate"):
            filt = params.get("filter")
            if isinstance(filt, dict) and filt.get("_id") and not params.get("collection"):
                inferred = infer_entity_from_text(query_text, backend="mongodb") or "portfolio"
                mapping = catalog.entity(inferred)
                if mapping:
                    entity_name = entity_name or inferred
                    if not params.get("database") and mapping.database:
                        params["database"] = mapping.database
                    if mapping.collection:
                        params["collection"] = mapping.collection

        email = extract_email(query_text)
        if (
            email
            and intent.operation in ("find", "count_documents")
            and not params.get("filter")
            and re.search(r"\busers?\b", query_text, re.I)
        ):
            mapping = catalog.entity("user")
            if mapping:
                entity_name = entity_name or "user"
                params = _apply_entity_mapping(
                    params,
                    mapping,
                    entity_id=None,
                    lookup_field="email",
                    lookup_value=email,
                )

        if intent.operation == "list_collections" and "portfolio" in query_text.lower():
            if not params.get("database"):
                params["database"] = catalog.default_database("mongodb") or "portfolio"

    if intent.backend == "postgres":
        if not params.get("schema"):
            default_schema = catalog.default_for("postgres", "schema")
            if default_schema:
                params["schema"] = default_schema

        uuid = extract_uuid(query_text)
        if uuid and intent.operation in POSTGRES_TABLE_OPS and not params.get("sql"):
            inferred = infer_entity_from_text(query_text, backend="postgres")
            if inferred:
                mapping = catalog.entity(inferred)
                if mapping:
                    entity_name = entity_name or inferred
                    params = _apply_entity_mapping(params, mapping, entity_id=entity_id)

        email = extract_email(query_text)
        if (
            email
            and intent.operation in POSTGRES_TABLE_OPS
            and not params.get("sql")
            and re.search(r"\busers?\b", query_text, re.I)
        ):
            mapping = catalog.entity("user_account")
            if mapping:
                entity_name = entity_name or "user_account"
                params = _apply_entity_mapping(
                    params,
                    mapping,
                    entity_id=None,
                    lookup_field="email",
                    lookup_value=email,
                )

        if intent.operation == "search_schema" and not params.get("pattern"):
            inferred = infer_entity_from_text(query_text, backend="postgres")
            if inferred:
                mapping = catalog.entity(inferred)
                if mapping and mapping.table:
                    entity_name = entity_name or inferred
                    params["pattern"] = mapping.table

    if intent.backend == "redis":
        uuid = extract_uuid(query_text)
        if uuid and intent.operation in REDIS_KEY_OPS and not params.get("key"):
            inferred = infer_entity_from_text(query_text, backend="redis")
            if inferred:
                mapping = catalog.entity(inferred)
                if mapping:
                    entity_name = entity_name or inferred
                    params = _apply_entity_mapping(params, mapping, entity_id=uuid)

        if intent.operation == "scan_keys" and not params.get("pattern"):
            inferred = infer_entity_from_text(query_text, backend="redis")
            if inferred:
                mapping = catalog.entity(inferred)
                if mapping and mapping.key_pattern:
                    entity_name = entity_name or inferred
                    params["pattern"] = mapping.key_pattern
            elif catalog.default_for("redis", "key_pattern"):
                params["pattern"] = catalog.default_for("redis", "key_pattern")

    if intent.backend == "qdrant" and intent.operation in QDRANT_COLL_OPS:
        if not params.get("collection"):
            inferred = infer_entity_from_text(query_text)
            if inferred:
                mapping = catalog.entity(inferred)
                if mapping and mapping.collection:
                    entity_name = entity_name or inferred
                    params["collection"] = mapping.collection

    intent = _maybe_upgrade_redis_operation(intent, params)

    missing = _missing_required_params(intent.backend, intent.operation, params)
    if missing:
        raise ParamResolutionError(missing)

    resolved_intent = intent.model_copy(update={"params": params})
    return resolved_intent, entity_name


def _missing_required_params(backend: str, operation: str, params: dict[str, Any]) -> str | None:
    if operation not in BACKEND_OPERATIONS.get(backend, []):
        return None

    if backend == "mongodb":
        if operation == "list_collections" and not params.get("database"):
            return (
                "Missing required param 'database' for mongodb.list_collections. "
                "Pass params.database or params.entity (portfolio, user)."
            )
        if operation in MONGO_DB_COLL_OPS - {"list_collections"}:
            if not params.get("database") or not params.get("collection"):
                return (
                    f"Missing database/collection for mongodb.{operation}. "
                    "Pass params.database + params.collection, or params.entity + params.id."
                )

    if backend == "postgres":
        if operation == "run_sql" and not params.get("sql"):
            return (
                "Missing required param 'sql' for postgres.run_sql. "
                "Pass params.sql, or params.entity + params.id / lookup_field + lookup_value."
            )
        if operation == "table_row_count" and not params.get("table"):
            return (
                "Missing required param 'table' for postgres.table_row_count. "
                "Pass params.table or params.entity (portfolio_pg, user_account)."
            )

    if backend == "redis":
        if operation == "get" and not params.get("key"):
            return (
                "Missing required param 'key' for redis.get. "
                "Pass params.key, or params.entity + params.id (e.g. session)."
            )
        if operation == "scan_keys" and not params.get("pattern"):
            return (
                "Missing required param 'pattern' for redis.scan_keys. "
                "Pass params.pattern or params.entity (session, portfolio_cache)."
            )

    if backend == "qdrant" and operation in QDRANT_COLL_OPS and not params.get("collection"):
        return (
            f"Missing required param 'collection' for qdrant.{operation}. "
            "Pass params.collection or params.entity (e.g. bug_memory)."
        )

    return None
