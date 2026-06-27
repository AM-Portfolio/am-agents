from __future__ import annotations

import asyncio
import difflib
from dataclasses import dataclass, field

from app.config import settings
from tools._shared.ttl_cache import TtlCache
from tools.vault.paths import normalize_vault_path

_cache: TtlCache["VaultPathSnapshot"] | None = None


@dataclass
class VaultPathSnapshot:
    paths: list[str] = field(default_factory=list)
    by_category: dict[str, list[str]] = field(default_factory=dict)


def _get_cache() -> TtlCache[VaultPathSnapshot]:
    global _cache
    if _cache is None:
        _cache = TtlCache(
            ttl_seconds=float(settings.VAULT_PATH_CACHE_TTL_SECONDS),
            enabled=settings.VAULT_PATH_CACHE_ENABLED,
        )
    return _cache


def _extract_keys(data: object) -> list[str]:
    if isinstance(data, dict):
        if "keys" in data and isinstance(data["keys"], list):
            return [str(k) for k in data["keys"]]
        inner = data.get("data")
        if isinstance(inner, dict):
            return _extract_keys(inner)
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


async def _refresh() -> VaultPathSnapshot:
    from tools.vault.adapter import VaultMcpAdapter

    adapter = VaultMcpAdapter()
    if not adapter.available:
        return VaultPathSnapshot()
    snapshot = VaultPathSnapshot()
    prefixes = ["preprod/infra", "preprod/services", "preprod/api"]
    for prefix in prefixes:
        try:
            result = await adapter.execute(
                "list_secrets",
                {"path": prefix, "mount": settings.VAULT_MCP_MOUNT or "apps"},
                read_only=True,
                max_rows=200,
            )
            keys = _extract_keys(result.get("data") if isinstance(result, dict) else result)
            category = prefix.split("/", 1)[1]
            leaves = []
            for key in keys:
                leaf = key.strip("/")
                full = normalize_vault_path(f"{prefix}/{leaf}" if leaf else prefix)
                leaves.append(full)
                snapshot.paths.append(full)
            snapshot.by_category[category] = leaves
        except Exception:
            continue
    return snapshot


async def refresh_path_cache() -> VaultPathSnapshot | None:
    return await _get_cache().get_or_refresh(_refresh)


def snapshot() -> VaultPathSnapshot | None:
    return _get_cache().snapshot()


def exists(path: str) -> bool:
    snap = snapshot()
    if not snap:
        return True
    normalized = normalize_vault_path(path)
    return normalized in snap.paths or any(normalized.startswith(p + "/") for p in snap.paths)


def fuzzy_match(token: str, *, known: list[str] | None = None, cutoff: float = 0.75) -> str | None:
    snap = snapshot()
    candidates = known or ([p.split("/")[-1] for p in snap.paths] if snap else [])
    if not candidates:
        return None
    key = token.lower().strip()
    if key in candidates:
        return key
    matches = difflib.get_close_matches(key, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def snippet(*, max_per_category: int = 20) -> str:
    snap = snapshot()
    if not snap or not snap.paths:
        return (
            "Vault paths: (cache offline — use convention preprod/{infra|services|api}/{leaf} "
            "or list_secrets on preprod/infra or preprod/services)"
        )
    lines = [f"Vault paths (live cache, mount apps, {len(snap.paths)} leaves):"]
    for category, paths in sorted(snap.by_category.items()):
        shown = paths[:max_per_category]
        extra = len(paths) - len(shown)
        suffix = f" (+{extra} more)" if extra > 0 else ""
        lines.append(f"  preprod/{category}: {', '.join(p.split('/')[-1] for p in shown)}{suffix}")
    lines.append("Use list_secrets for discovery.")
    return "\n".join(lines)


def catalog_source() -> str:
    cache = _get_cache()
    if not cache.enabled:
        return "offline"
    return "live" if cache.is_fresh() else "stale"


def reset_cache_for_tests() -> None:
    global _cache
    if _cache:
        _cache.clear()
    _cache = None
