from __future__ import annotations

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog
from tools._shared.intent_trace import set_resolve_trace
from tools.vault.paths import normalize_vault_path
from tools.vault.path_cache import catalog_source, exists, fuzzy_match, snapshot
from tools.vault.search.convention import resolve_convention, to_params


def _fuzzy_path_leaf(path: str, token: str) -> str | None:
    snap = snapshot()
    if not snap:
        return None
    normalized = normalize_vault_path(path)
    prefix = normalized.rsplit("/", 1)[0] if "/" in normalized else normalized
    candidates = [p for p in snap.paths if p.startswith(prefix + "/") or p == prefix]
    if not candidates:
        candidates = snap.paths
    return fuzzy_match(token, known=[p.split("/")[-1] for p in candidates])


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    params = dict(intent.params)
    entity_name = params.pop("entity", None)
    method = "entity" if entity_name else "passthrough"

    catalog = get_schema_catalog()
    if entity_name:
        mapping = catalog.entity(str(entity_name))
        if mapping and mapping.collection:
            params.setdefault("path", normalize_vault_path(str(mapping.collection)))
            entity_name = str(entity_name)

    if not params.get("path") and intent.operation in {"list_secrets", "read_secret", "write_secret", "delete_secret"}:
        prefix = catalog.default_for("vault", "path_prefix") or "preprod"
        params.setdefault("path", normalize_vault_path(f"apps/{prefix}"))

    if params.get("path"):
        params["path"] = normalize_vault_path(str(params["path"]))
    elif intent.operation in {"list_secrets", "read_secret", "write_secret", "delete_secret"} and query:
        result = resolve_convention(query, default_operation=intent.operation)
        fuzzy_params = to_params(result)
        if fuzzy_params.get("path"):
            params["path"] = normalize_vault_path(str(fuzzy_params["path"]))
            method = result.resolve_method
        if fuzzy_params.get("entity"):
            entity_name = str(fuzzy_params["entity"])

    if params.get("path") and not exists(str(params["path"])):
        leaf = str(params["path"]).split("/")[-1]
        fuzzy_leaf = _fuzzy_path_leaf(str(params["path"]), leaf)
        if fuzzy_leaf:
            prefix = "/".join(str(params["path"]).split("/")[:-1])
            params["path"] = normalize_vault_path(f"{prefix}/{fuzzy_leaf}")
            method = "cache_fuzzy"

    mount = catalog.default_for("vault", "mount")
    if mount:
        params.setdefault("mount", mount)

    matched = str(params.get("path", "")).replace("apps/", "")
    set_resolve_trace(
        resolve_method=method,
        matched_key=matched or None,
        catalog_source=catalog_source(),
    )
    return intent.model_copy(update={"params": params}), entity_name
