from __future__ import annotations

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog
from tools._shared.resolve import resolve_intent_params


def _apply_grafana_defaults(intent: IntentDocument) -> IntentDocument:
    catalog = get_schema_catalog()
    params = dict(intent.params)
    ds_uid = catalog.default_for("grafana", "loki_datasource_uid")
    if ds_uid and intent.operation in (
        "query_logs",
        "list_labels",
        "list_label_values",
        "query_patterns",
        "find_error_logs",
    ):
        params.setdefault("datasourceUid", ds_uid)
    if intent.operation in ("query_logs", "query_metrics", "find_error_logs"):
        params.setdefault("start", catalog.default_for("grafana", "start") or "now-1h")
        params.setdefault("end", catalog.default_for("grafana", "end") or "now")
    return intent.model_copy(update={"params": params})


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    resolved, entity = resolve_intent_params(intent, query_text=query)
    resolved = _apply_grafana_defaults(resolved)
    return resolved, entity
