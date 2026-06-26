from __future__ import annotations

from dataclasses import dataclass

from tools.vault.search.convention import (
    VaultConventionResult,
    env_from_query,
    resolve_convention,
    to_params,
)


@dataclass(frozen=True)
class VaultTarget:
    env: str
    category: str | None
    entity: str | None
    path: str | None
    operation: str
    confidence: float
    rationale: str


def resolve_vault_target(query: str, *, default_operation: str = "read_secret") -> VaultTarget:
    result = resolve_convention(query, default_operation=default_operation)
    env = env_from_query(query)
    path = result.path
    category = path.split("/")[1] if path and "/" in path else None
    return VaultTarget(
        env=env,
        category=category,
        entity=result.entity,
        path=path,
        operation=result.operation,
        confidence=result.confidence,
        rationale=result.rationale,
    )


def target_to_params(target: VaultTarget) -> dict[str, str]:
    return to_params(
        VaultConventionResult(
            path=target.path,
            operation=target.operation,
            confidence=target.confidence,
            rationale=target.rationale,
            entity=target.entity,
        )
    )


def fuzzy_entity_from_query(query: str, *, catalog=None) -> str | None:
    _ = catalog
    return resolve_convention(query).entity
