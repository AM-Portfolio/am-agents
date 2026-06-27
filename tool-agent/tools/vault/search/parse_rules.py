from __future__ import annotations

import re

from app.models.intent import IntentDocument
from tools.vault.search.fuzzy import resolve_vault_target, target_to_params

_PATH_RE = re.compile(
    r"(?:apps/data/|apps/)(?:dev|preprod|prod)/(?:infra|services|api)/[\w./-]+",
    re.I,
)
_VAULT_KW = re.compile(r"\b(vault|hashicorp|kv)\b", re.I)
_SECRET_KW = re.compile(r"\b(secret|secrets|credential|credentials)\b", re.I)


def _matches_vault_query(query: str, *, tool_name: str, backend_hint: str | None) -> bool:
    if backend_hint == tool_name:
        return True
    if _VAULT_KW.search(query):
        return True
    if _SECRET_KW.search(query) and re.search(r"\b(list|read|show|get|under)\b", query, re.I):
        return True
    return bool(_PATH_RE.search(query))


def _entity_from_query(query: str) -> str | None:
    from tools.vault.search.fuzzy import fuzzy_entity_from_query

    return fuzzy_entity_from_query(query)


def _path_from_query(query: str) -> str | None:
    match = _PATH_RE.search(query)
    if match:
        return match.group(0)
    target = resolve_vault_target(query)
    if target.path:
        return f"apps/{target.path}"
    return None


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    if not _matches_vault_query(query, tool_name=tool_name, backend_hint=backend_hint):
        return None

    q = query.lower()

    if re.search(r"\blist\b.*\bmounts?\b|\bmounts?\s+in\s+vault\b", q):
        return IntentDocument(
            backend=tool_name,
            operation="list_mounts",
            params={},
            confidence=0.9,
            rationale="Rule: list vault mounts",
        )

    if re.search(r"\b(write|set|update|put|create)\b", q):
        target = resolve_vault_target(query, default_operation="write_secret")
        params = target_to_params(target)
        key_match = re.search(r"\bkey\s+['\"]?([\w.-]+)['\"]?", query, re.I)
        if key_match:
            params["key"] = key_match.group(1)
        return IntentDocument(
            backend=tool_name,
            operation="write_secret",
            params=params,
            read_only=False,
            confidence=target.confidence,
            rationale=target.rationale,
        )

    if re.search(r"\bdelete\b", q):
        target = resolve_vault_target(query, default_operation="delete_secret")
        return IntentDocument(
            backend=tool_name,
            operation="delete_secret",
            params=target_to_params(target),
            read_only=False,
            confidence=target.confidence,
            rationale=target.rationale,
        )

    target = resolve_vault_target(query)
    return IntentDocument(
        backend=tool_name,
        operation=target.operation,
        params=target_to_params(target),
        confidence=target.confidence,
        rationale=target.rationale,
    )
