from __future__ import annotations

import copy
import re
from typing import Any

from app.models.intent import IntentDocument
from app.schema.loader import (
    EntityMapping,
    get_schema_catalog,
    postgres_select_by_field,
    postgres_select_sql,
)
from tools._shared.extract import extract_email, extract_uuid

MONGO_DB_COLL_OPS = frozenset(
    {"find", "aggregate", "count_documents", "collection_schema", "list_collections"}
)
QDRANT_COLL_OPS = frozenset({"collection_info", "scroll", "search"})
POSTGRES_TABLE_OPS = frozenset({"run_sql", "table_row_count", "search_schema"})
REDIS_KEY_OPS = frozenset({"get", "type", "scan_keys"})

BACKEND_OPERATIONS: dict[str, list[str]] = {
    "mongodb": [
        "list_databases", "list_collections", "find", "aggregate",
        "collection_schema", "count_documents",
    ],
    "postgres": ["search_schema", "run_sql", "table_row_count"],
    "redis": ["scan_keys", "get", "info", "type"],
    "kafka": ["list_topics", "describe_topic", "peek_messages", "consumer_lag"],
    "qdrant": ["list_collections", "collection_info", "scroll", "search"],
    "grafana": [
        "query_logs",
        "list_labels",
        "list_label_values",
        "query_patterns",
        "find_error_logs",
        "query_metrics",
        "search_dashboards",
        "get_dashboard",
        "list_datasources",
    ],
    "vault": ["list_mounts", "list_secrets", "read_secret", "write_secret", "delete_secret"],
}

_ENTITY_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"mutual\s+funds?.*portfolios?|mutual\s+fund\s+portfolio", re.I), "mutual_fund_portfolio"),
    (re.compile(r"\betfs?\b", re.I), "etf"),
    (re.compile(r"trade[_\s-]?details?", re.I), "trade_detail"),
    (re.compile(r"portfolio[_\s-]?trades?", re.I), "portfolio_trade"),
    (re.compile(r"market[_\s-]?data.*securities|securities.*market[_\s-]?data", re.I), "market_security"),
    (re.compile(r"market[_\s-]?instruments?|instruments?.*market[_\s-]?data", re.I), "market_instrument"),
    (re.compile(r"\bsecurities\b", re.I), "portfolio_security"),
    (re.compile(r"\btrades?\b", re.I), "trade"),
    (re.compile(r"\bsessions?\b"), "session"),
    (re.compile(r"\busers?\b"), "user"),
    (re.compile(r"\bportfolios?\b"), "portfolio"),
    (re.compile(r"bug_memory|bug memory", re.I), "bug_memory"),
]


class ParamResolutionError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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


def _apply_entity_mapping(
    params: dict[str, Any],
    mapping: EntityMapping,
    *,
    entity_id: str | None,
    lookup_field: str | None = None,
    lookup_value: str | None = None,
) -> dict[str, Any]:
    resolved = dict(params)
    for key in ("entity", "id", "lookup_field", "lookup_value"):
        if key in resolved and locals().get(key.replace("lookup_", "lookup_") if False else key):
            pass
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
            resolved = _apply_lookup(mapping, resolved, lookup_field=lookup_field, lookup_value=lookup_value)
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
            resolved = _apply_lookup(mapping, resolved, lookup_field=lookup_field, lookup_value=lookup_value)
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
    if intent.backend == "redis" and intent.operation == "scan_keys" and params.get("key"):
        return intent.model_copy(update={"operation": "get"})
    return intent


def _resolve_vault_entity_param(
    entity_name: str,
    params: dict[str, Any],
    *,
    query_text: str,
    catalog: Any,
) -> tuple[dict[str, Any], str | None]:
    """Map vault service/infra entity tokens to KV paths without catalog entries."""
    from tools.vault.paths import normalize_vault_path
    from tools.vault.search.convention import build_path, env_from_query

    if params.get("path"):
        return params, None

    env = env_from_query(query_text) if query_text else (catalog.default_for("vault", "env") or "preprod")
    name = entity_name.lower()
    if name.endswith("_infra"):
        leaf = name[:-6].replace("_", "-")
        params["path"] = normalize_vault_path(build_path(env, "infra", leaf))
        return params, None
    if name.startswith("am_"):
        leaf = name.replace("_", "-")
        params["path"] = normalize_vault_path(build_path(env, "services", leaf))
        return params, None
    alias = catalog.vault_path_alias(name.replace("_", "-"))
    if alias:
        category = "infra" if alias in (catalog.vault_infra_components() or []) else "services"
        params["path"] = normalize_vault_path(build_path(env, category, alias))
        return params, None
    raise ParamResolutionError(f"Unknown entity '{entity_name}' in schema catalog")


def resolve_intent_params(
    intent: IntentDocument,
    *,
    query_text: str = "",
) -> tuple[IntentDocument, str | None]:
    catalog = get_schema_catalog()
    params = copy.deepcopy(intent.params)
    entity_name: str | None = params.pop("entity", None) or None
    entity_id: str | None = params.pop("id", None) or None
    lookup_field: str | None = params.pop("lookup_field", None) or None
    lookup_value: str | None = params.pop("lookup_value", None) or None

    if entity_name:
        if intent.backend == "vault" and params.get("path"):
            from tools.vault.paths import normalize_vault_path

            params["path"] = normalize_vault_path(str(params["path"]))
            entity_name = None
        else:
            mapping = catalog.entity(entity_name)
            if not mapping:
                if intent.backend == "vault":
                    params, entity_name = _resolve_vault_entity_param(
                        entity_name, params, query_text=query_text, catalog=catalog
                    )
                else:
                    raise ParamResolutionError(f"Unknown entity '{entity_name}' in schema catalog")
            elif mapping.backend != intent.backend:
                raise ParamResolutionError(
                    f"Entity '{entity_name}' maps to backend '{mapping.backend}', not '{intent.backend}'"
                )
            else:
                params = _apply_entity_mapping(
                    params, mapping, entity_id=entity_id,
                    lookup_field=lookup_field, lookup_value=lookup_value,
                )
    elif lookup_field and lookup_value:
        inferred = infer_entity_from_text(query_text, backend=intent.backend)
        if inferred:
            mapping = catalog.entity(inferred)
            if mapping and mapping.backend == intent.backend:
                entity_name = inferred
                params = _apply_entity_mapping(
                    params, mapping, entity_id=entity_id,
                    lookup_field=lookup_field, lookup_value=lookup_value,
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
        if intent.operation == "list_collections" and "portfolio" in query_text.lower():
            if not params.get("database"):
                params["database"] = catalog.default_database("mongodb") or "portfolio"

    if intent.backend == "postgres":
        if not params.get("schema"):
            default_schema = catalog.default_for("postgres", "schema")
            if default_schema:
                params["schema"] = default_schema
        email = extract_email(query_text)
        if email and intent.operation in POSTGRES_TABLE_OPS and not params.get("sql"):
            if re.search(r"\busers?\b", query_text, re.I):
                mapping = catalog.entity("user_account")
                if mapping:
                    entity_name = entity_name or "user_account"
                    params = _apply_entity_mapping(
                        params, mapping, entity_id=None,
                        lookup_field="email", lookup_value=email,
                    )

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
    return intent.model_copy(update={"params": params}), entity_name


def _missing_required_params(backend: str, operation: str, params: dict[str, Any]) -> str | None:
    if operation not in BACKEND_OPERATIONS.get(backend, []):
        return None
    if backend == "mongodb" and operation in MONGO_DB_COLL_OPS - {"list_collections"}:
        if not params.get("database") or not params.get("collection"):
            return f"Missing database/collection for mongodb.{operation}"
    if backend == "postgres" and operation == "run_sql" and not params.get("sql"):
        return "Missing sql for postgres.run_sql"
    if backend == "postgres" and operation == "table_row_count" and not params.get("table"):
        return "Missing table for postgres.table_row_count (use params.entity)"
    if backend == "redis" and operation == "get" and not params.get("key"):
        return "Missing key for redis.get"
    if backend == "qdrant" and operation in QDRANT_COLL_OPS and not params.get("collection"):
        return f"Missing collection for qdrant.{operation}"
    if backend == "kafka" and operation in {"describe_topic", "peek_messages"} and not params.get("topic"):
        return f"Missing topic for kafka.{operation}"
    if backend == "grafana" and operation == "query_logs":
        if not (params.get("query") or params.get("logql")):
            return "Missing query/logql for grafana.query_logs"
    if backend == "grafana" and operation == "get_dashboard" and not (
        params.get("uid") or params.get("dashboardUid")
    ):
        return "Missing uid for grafana.get_dashboard"
    if backend == "vault" and operation in {"list_secrets", "read_secret", "write_secret", "delete_secret"}:
        if not params.get("path") and not params.get("entity"):
            return f"Missing path or entity for vault.{operation}"
    return None
