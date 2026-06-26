from __future__ import annotations

import re
from dataclasses import dataclass

from app.schema.loader import get_schema_catalog
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
        "read", "get", "show", "fetch", "list", "secret", "secrets", "vault",
        "hashicorp", "kv", "under", "from", "in", "for", "the", "a", "an",
        "apps", "data", "preprod", "prod", "dev", "infra", "infrastructure",
        "service", "services", "api", "all",
    }
)
_INFRA_BOOST: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpostgre?s{1,2}\b|\bpg\b", re.I), "postgres"),
    (re.compile(r"\bmongo(?:db)?\b", re.I), "mongodb"),
    (re.compile(r"\bredis\b", re.I), "redis"),
    (re.compile(r"\bkafka\b", re.I), "kafka"),
    (re.compile(r"\binflux(?:db)?\b", re.I), "influxdb"),
    (re.compile(r"\bshared[-\s]?api\b", re.I), "shared-api"),
]
_SERVICE_RE = re.compile(r"\b(am-[a-z0-9-]+)\b", re.I)
_SERVICE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmcp[-\s]?gateway\b|\bobservability\b", re.I), "am-mcp-gateway"),
    (re.compile(r"\bidentity\b|\bam[-\s]?identity\b", re.I), "am-identity"),
    (re.compile(r"\bkeycloak\b", re.I), "am-keycloak"),
    (re.compile(r"\bwebsocket\s+gateway\b|\bam[-\s]?gateway\b", re.I), "am-gateway"),
    (re.compile(r"\bam[-\s]?analysis\b|\banalysis\b", re.I), "am-analysis"),
    (re.compile(r"\bam[-\s]?portfolio\b|\bportfolio\s+service\b", re.I), "am-portfolio"),
    (re.compile(r"\bam[-\s]?notification\b|\bnotification\b", re.I), "am-notification"),
    (re.compile(r"\bam[-\s]?parser\b|\bparser\b", re.I), "am-parser"),
    (re.compile(r"\bam[-\s]?subscription\b|\bsubscription\b", re.I), "am-subscription"),
    (re.compile(r"\bam[-\s]?trade\b|\btrade[-\s]?management\b", re.I), "am-trade-management"),
    (re.compile(r"\bam[-\s]?market[-\s]?data\b|\bmarket[-\s]?data\b", re.I), "am-market-data"),
    (re.compile(r"\bam[-\s]?lago\b|\blago\b", re.I), "am-lago"),
    (re.compile(r"\bam[-\s]?novu\b|\bnovu\b", re.I), "am-novu"),
    (re.compile(r"\bam[-\s]?tool[-\s]?agent\b|\btool[-\s]?agent\b", re.I), "am-tool-agent"),
    (re.compile(r"\bam[-\s]?auth\b", re.I), "am-auth"),
]


@dataclass(frozen=True)
class VaultConventionResult:
    path: str | None
    operation: str
    confidence: float
    rationale: str
    resolve_method: str = "convention"
    entity: str | None = None


def env_from_query(query: str) -> str:
    catalog = get_schema_catalog()
    match = _ENV_RE.search(query)
    if match:
        return match.group(1).lower()
    return (catalog.default_for("vault", "env") or "preprod").lower()


def category_from_query(query: str) -> str | None:
    for pattern, category in _CATEGORY_PATTERNS:
        if pattern.search(query):
            return category
    return None


def _tokens(query: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[\w-]+", query.lower())
        if token not in _STOPWORDS and len(token) > 1
    ]


def _infra_component(query: str) -> str | None:
    for pattern, component in _INFRA_BOOST:
        if pattern.search(query):
            return component
    catalog = get_schema_catalog()
    for token in _tokens(query):
        alias = catalog.vault_path_alias(token)
        if alias and alias in (catalog.vault_infra_components() or []):
            return alias
    return None


def _service_leaf(query: str) -> str | None:
    match = _SERVICE_RE.search(query)
    if match:
        return match.group(1).lower()
    for pattern, service in _SERVICE_HINTS:
        if pattern.search(query):
            return service
    catalog = get_schema_catalog()
    for token in _tokens(query):
        alias = catalog.vault_path_alias(token)
        if alias and alias.startswith("am-"):
            return alias
    return None


def build_path(env: str, category: str, leaf: str) -> str:
    return normalize_vault_path(f"{env}/{category}/{leaf.strip('/')}")


def _entity_for_infra(leaf: str) -> str:
    if leaf == "shared-api":
        return "shared_api_infra"
    return f"{leaf.replace('-', '_')}_infra"


def _entity_for_service(service: str) -> str:
    return service.lower().replace("-", "_")


def resolve_convention(query: str, *, default_operation: str = "read_secret") -> VaultConventionResult:
    catalog = get_schema_catalog()
    env = env_from_query(query)
    category = category_from_query(query)
    infra = _infra_component(query)
    service = _service_leaf(query)

    if infra and not service:
        path = build_path(env, "infra", infra)
        op = "list_secrets" if _LIST_RE.search(query) and not _READ_SECRET_RE.search(query) else "read_secret"
        return VaultConventionResult(
            path=path,
            operation=op,
            confidence=0.88,
            rationale=f"Infra component '{infra}'",
            entity=_entity_for_infra(infra),
        )

    if service:
        path = build_path(env, "services", service)
        return VaultConventionResult(
            path=path,
            operation="read_secret",
            confidence=0.9,
            rationale=f"Service path convention am-* → {service}",
            entity=_entity_for_service(service),
        )

    if category:
        prefix = build_path(env, category, "").rstrip("/")
        if category == "infra" and infra:
            path = build_path(env, category, infra)
            op = "read_secret" if _READ_SECRET_RE.search(query) else "list_secrets"
            return VaultConventionResult(path=path, operation=op, confidence=0.82, rationale=f"Category+infra {infra}")
        if _LIST_RE.search(query) and not _READ_SECRET_RE.search(query):
            return VaultConventionResult(
                path=prefix,
                operation="list_secrets",
                confidence=0.82,
                rationale=f"List category '{category}'",
            )
        if _READ_SECRET_RE.search(query):
            tokens = _tokens(query)
            if tokens:
                path = build_path(env, category, tokens[0])
                return VaultConventionResult(
                    path=path,
                    operation="read_secret",
                    confidence=0.76,
                    rationale=f"Category '{category}' + leaf '{tokens[0]}'",
                )
            default_leaf = catalog.vault_category_default_leaf(category)
            if default_leaf:
                path = build_path(env, category, default_leaf)
                return VaultConventionResult(
                    path=path,
                    operation="read_secret",
                    confidence=0.74,
                    rationale=f"Category '{category}' default leaf",
                )
        return VaultConventionResult(
            path=prefix,
            operation="list_secrets",
            confidence=0.78,
            rationale=f"Category prefix '{category}'",
        )

    if _LIST_RE.search(query):
        return VaultConventionResult(
            path=build_path(env, "infra", "").rstrip("/"),
            operation="list_secrets",
            confidence=0.7,
            rationale="Default list infra",
        )

    return VaultConventionResult(
        path=build_path(env, "infra", "").rstrip("/"),
        operation=default_operation,
        confidence=0.65,
        rationale="Vault convention fallback",
    )


def to_params(result: VaultConventionResult) -> dict[str, str]:
    params: dict[str, str] = {}
    if result.entity:
        params["entity"] = result.entity
    if result.path:
        params["path"] = f"apps/{result.path}" if not result.path.startswith("apps/") else result.path
    return params
