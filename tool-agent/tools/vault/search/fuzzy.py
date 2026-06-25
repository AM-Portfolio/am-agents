from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from app.schema.loader import SchemaCatalog, get_schema_catalog
from tools.vault.paths import normalize_vault_path

_ENV_RE = re.compile(r"\b(preprod|prod|dev)\b", re.I)
_READ_SECRET_RE = re.compile(
    r"\b(read|get|show|fetch)\b.*\bsecret\b|\bsecret\b.*\b(read|get|show|fetch)\b", re.I
)
_LIST_RE = re.compile(r"\b(list|show\s+all|under)\b", re.I)
_CATEGORY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bservices?\b|\bapp[-\s]?services?\b", re.I), "services"),
    (re.compile(r"\binfra(?:structure)?\b", re.I), "infra"),
    (re.compile(r"\bapi\b", re.I), "api"),
]
_STOPWORDS = frozenset(
    {
        "read",
        "get",
        "show",
        "fetch",
        "list",
        "secret",
        "secrets",
        "vault",
        "hashicorp",
        "kv",
        "under",
        "from",
        "in",
        "for",
        "the",
        "a",
        "an",
        "apps",
        "data",
        "preprod",
        "prod",
        "dev",
        "infra",
        "infrastructure",
        "service",
        "services",
        "api",
        "all",
    }
)
_ENTITY_BOOST: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpostgre?s{1,2}\b|\bpg\b", re.I), "postgres_infra"),
    (re.compile(r"\bmongo(?:db)?\b", re.I), "mongodb_infra"),
    (re.compile(r"\bredis\b", re.I), "redis_infra"),
    (re.compile(r"\bkafka\b", re.I), "kafka_infra"),
    (re.compile(r"\binflux(?:db)?\b", re.I), "influxdb_infra"),
    (re.compile(r"\bidentity\b|\bam[-\s]?identity\b", re.I), "am_identity"),
    (re.compile(r"\bmcp[-\s]?gateway\b|\bobservability\b|\bgateway\b", re.I), "am_mcp_gateway"),
    (re.compile(r"\bkeycloak\b|\bauth\b", re.I), "am_keycloak"),
    (re.compile(r"\bshared[-\s]?api\b", re.I), "shared_api_infra"),
]


@dataclass(frozen=True)
class VaultTarget:
    env: str
    category: str | None
    entity: str | None
    path: str | None
    operation: str
    confidence: float
    rationale: str


def _tokens(query: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[\w-]+", query.lower())
        if token not in _STOPWORDS and len(token) > 1
    ]


def env_from_query(query: str, *, catalog: SchemaCatalog | None = None) -> str:
    catalog = catalog or get_schema_catalog()
    match = _ENV_RE.search(query)
    if match:
        return match.group(1).lower()
    return (catalog.default_for("vault", "env") or "preprod").lower()


def category_from_query(query: str) -> str | None:
    for pattern, category in _CATEGORY_PATTERNS:
        if pattern.search(query):
            return category
    return None


def _entity_keywords(entity_name: str, collection: str | None) -> list[str]:
    keywords = [entity_name.replace("_", "-"), entity_name.replace("_", " ")]
    if collection:
        leaf = collection.split("/")[-1]
        keywords.extend([leaf, leaf.replace("-", " "), leaf.replace("-", "_")])
        for part in collection.split("/"):
            if part not in {"preprod", "prod", "dev", "infra", "services", "api"}:
                keywords.append(part)
    return [k.lower() for k in keywords if k]


def fuzzy_entity_from_query(query: str, *, catalog: SchemaCatalog | None = None) -> str | None:
    catalog = catalog or get_schema_catalog()
    for pattern, entity in _ENTITY_BOOST:
        if pattern.search(query):
            return entity

    tokens = _tokens(query)
    if not tokens:
        return None

    best_entity: str | None = None
    best_score = 0.0
    for mapping in catalog.entities_for_backend("vault"):
        keywords = _entity_keywords(mapping.name, mapping.collection)
        for token in tokens:
            for keyword in keywords:
                if token == keyword or token in keyword or keyword in token:
                    score = 0.95 + min(len(token), len(keyword)) * 0.01
                    if score > best_score:
                        best_score = score
                        best_entity = mapping.name
                close = difflib.get_close_matches(token, [keyword], n=1, cutoff=0.72)
                if close:
                    score = 0.82 + len(close[0]) * 0.01
                    if score > best_score:
                        best_score = score
                        best_entity = mapping.name
    return best_entity if best_score >= 0.8 else None


def _category_prefix(env: str, category: str) -> str:
    return normalize_vault_path(f"{env}/{category}")


def resolve_vault_target(query: str, *, default_operation: str = "read_secret") -> VaultTarget:
    catalog = get_schema_catalog()
    env = env_from_query(query, catalog=catalog)
    category = category_from_query(query)
    entity = fuzzy_entity_from_query(query, catalog=catalog)

    if entity:
        mapping = catalog.entity(entity)
        path = normalize_vault_path(str(mapping.collection)) if mapping and mapping.collection else None
        return VaultTarget(
            env=env,
            category=(path.split("/")[1] if path and "/" in path else category),
            entity=entity,
            path=path,
            operation="read_secret",
            confidence=0.9,
            rationale=f"Fuzzy matched vault entity '{entity}'",
        )

    if category:
        prefix = _category_prefix(env, category)
        if _LIST_RE.search(query) or (_READ_SECRET_RE.search(query) and not _tokens(query)):
            return VaultTarget(
                env=env,
                category=category,
                entity=None,
                path=prefix,
                operation="list_secrets",
                confidence=0.82,
                rationale=f"Category '{category}' without specific secret — list under {prefix}",
            )
        tokens = _tokens(query)
        if tokens and _READ_SECRET_RE.search(query):
            leaf = tokens[0]
            path = normalize_vault_path(f"{env}/{category}/{leaf}")
            return VaultTarget(
                env=env,
                category=category,
                entity=None,
                path=path,
                operation="read_secret",
                confidence=0.75,
                rationale=f"Fuzzy path from category '{category}' + token '{leaf}'",
            )
        return VaultTarget(
            env=env,
            category=category,
            entity=None,
            path=prefix,
            operation="list_secrets",
            confidence=0.8,
            rationale=f"Mapped vault category '{category}' to prefix {prefix}",
        )

    if _LIST_RE.search(query) or _READ_SECRET_RE.search(query):
        prefix = _category_prefix(env, "infra")
        return VaultTarget(
            env=env,
            category="infra",
            entity=None,
            path=prefix,
            operation="list_secrets" if _LIST_RE.search(query) else default_operation,
            confidence=0.7,
            rationale=f"Env '{env}' only — default infra prefix {prefix}",
        )

    return VaultTarget(
        env=env,
        category=None,
        entity=None,
        path=_category_prefix(env, "infra"),
        operation=default_operation,
        confidence=0.65,
        rationale="Vault fuzzy fallback",
    )


def target_to_params(target: VaultTarget) -> dict[str, str]:
    params: dict[str, str] = {}
    if target.entity:
        params["entity"] = target.entity
    if target.path:
        params["path"] = f"apps/{target.path}" if not target.path.startswith("apps/") else target.path
    return params
