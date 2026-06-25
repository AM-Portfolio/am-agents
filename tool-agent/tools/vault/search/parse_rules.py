from __future__ import annotations

import re

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog

_VAULT_KW = re.compile(r"\b(vault|hashicorp|kv)\b", re.I)
_SECRET_KW = re.compile(r"\b(secret|secrets|credential|credentials)\b", re.I)
_PATH_RE = re.compile(
    r"(?:apps/data/|apps/)(?:dev|preprod|prod)/(?:infra|services|api)/[\w./-]+",
    re.I,
)
_ENTITY_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpostgres\b", re.I), "postgres_infra"),
    (re.compile(r"\bmongo(?:db)?\b", re.I), "mongodb_infra"),
    (re.compile(r"\bredis\b", re.I), "redis_infra"),
    (re.compile(r"\bkafka\b", re.I), "kafka_infra"),
    (re.compile(r"\binflux(?:db)?\b", re.I), "influxdb_infra"),
    (re.compile(r"\bidentity\b|\bam-identity\b", re.I), "am_identity"),
    (re.compile(r"\bmcp[-\s]?gateway\b|\bobservability\b", re.I), "am_mcp_gateway"),
    (re.compile(r"\bkeycloak\b", re.I), "am_keycloak"),
    (re.compile(r"\bshared[-\s]?api\b", re.I), "shared_api_infra"),
]


def _matches_vault_query(query: str, *, tool_name: str, backend_hint: str | None) -> bool:
    if backend_hint == tool_name:
        return True
    if _VAULT_KW.search(query):
        return True
    if _SECRET_KW.search(query) and re.search(r"\b(list|read|show|get|under)\b", query, re.I):
        return True
    return bool(_PATH_RE.search(query))


def _entity_from_query(query: str) -> str | None:
    for pattern, entity in _ENTITY_ALIASES:
        if pattern.search(query):
            return entity
    return None


def _path_from_query(query: str) -> str | None:
    match = _PATH_RE.search(query)
    if match:
        return match.group(0)
    catalog = get_schema_catalog()
    entity = _entity_from_query(query)
    if entity:
        mapping = catalog.entity(entity)
        if mapping and mapping.collection:
            return f"apps/{mapping.collection}"
    if re.search(r"\binfra\b", query, re.I):
        prefix = catalog.default_for("vault", "path_prefix") or "data/preprod"
        return f"apps/{prefix}/infra"
    if re.search(r"\bservices\b", query, re.I):
        prefix = catalog.default_for("vault", "path_prefix") or "data/preprod"
        return f"apps/{prefix}/services"
    return None


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    if not _matches_vault_query(query, tool_name=tool_name, backend_hint=backend_hint):
        return None

    q = query.lower()
    path = _path_from_query(query)
    entity = _entity_from_query(query)

    if re.search(r"\blist\b.*\bmounts?\b|\bmounts?\s+in\s+vault\b", q):
        return IntentDocument(
            backend=tool_name,
            operation="list_mounts",
            params={},
            confidence=0.9,
            rationale="Rule: list vault mounts",
        )

    if re.search(r"\blist\b|\bshow\s+all\b|\bunder\b", q):
        params: dict[str, str] = {}
        if path:
            params["path"] = path
        elif entity:
            params["entity"] = entity
        else:
            prefix = get_schema_catalog().default_for("vault", "path_prefix") or "data/preprod"
            params["path"] = f"apps/{prefix}"
        return IntentDocument(
            backend=tool_name,
            operation="list_secrets",
            params=params,
            confidence=0.88,
            rationale="Rule: list vault secrets under path",
        )

    if re.search(r"\b(write|set|update|put|create)\b", q):
        params_w: dict[str, str] = {}
        if entity:
            params_w["entity"] = entity
        if path:
            params_w["path"] = path
        key_match = re.search(r"\bkey\s+['\"]?([\w.-]+)['\"]?", query, re.I)
        if key_match:
            params_w["key"] = key_match.group(1)
        return IntentDocument(
            backend=tool_name,
            operation="write_secret",
            params=params_w,
            read_only=False,
            confidence=0.75,
            rationale="Rule: vault write secret (requires /plan + /execute confirmation)",
        )

    if re.search(r"\bdelete\b", q):
        params_d: dict[str, str] = {}
        if entity:
            params_d["entity"] = entity
        if path:
            params_d["path"] = path
        return IntentDocument(
            backend=tool_name,
            operation="delete_secret",
            params=params_d,
            read_only=False,
            confidence=0.75,
            rationale="Rule: vault delete secret (requires /plan + /execute confirmation)",
        )

    params_r: dict[str, str] = {}
    if entity:
        params_r["entity"] = entity
    if path:
        params_r["path"] = path
    return IntentDocument(
        backend=tool_name,
        operation="read_secret",
        params=params_r,
        confidence=0.85,
        rationale="Rule: read vault secret",
    )
