from __future__ import annotations

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    _ = query
    params = dict(intent.params)
    entity_name = params.pop("entity", None)

    catalog = get_schema_catalog()
    if entity_name:
        mapping = catalog.entity(str(entity_name))
        if mapping and mapping.collection:
            params.setdefault("path", mapping.collection)
            entity_name = str(entity_name)

    if not params.get("path") and intent.operation in {"list_secrets", "read_secret", "write_secret", "delete_secret"}:
        prefix = catalog.default_for("vault", "path_prefix") or "data/preprod"
        params.setdefault("path", f"apps/{prefix}")

    mount = catalog.default_for("vault", "mount")
    if mount:
        params.setdefault("mount", mount)

    return intent.model_copy(update={"params": params}), entity_name
