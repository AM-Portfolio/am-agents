from __future__ import annotations

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog
from tools._shared.intent_trace import set_resolve_trace
from tools.kafka.search.convention import normalize_topic, resolve_topic_param
from tools.kafka.topic_cache import catalog_source, exists, fuzzy_match
from tools.vault.paths import normalize_vault_path


def resolve(intent: IntentDocument, query: str) -> tuple[IntentDocument, str | None]:
    params = dict(intent.params)
    entity_name = params.pop("entity", None)
    params, matched, method = resolve_topic_param(params, query)
    if matched:
        topic = str(matched)
        if not exists(topic):
            fuzzy = fuzzy_match(topic)
            if fuzzy:
                topic = fuzzy
                method = "cache_fuzzy"
        params["topic"] = normalize_topic(topic)
        set_resolve_trace(
            resolve_method=method,
            matched_key=params["topic"],
            catalog_source=catalog_source(),
        )
    elif entity_name:
        mapping = get_schema_catalog().entity(str(entity_name))
        if mapping and mapping.backend == intent.backend and mapping.collection:
            params["topic"] = normalize_topic(str(mapping.collection))
            set_resolve_trace(
                resolve_method="entity",
                matched_key=params["topic"],
                catalog_source=catalog_source(),
            )
    return intent.model_copy(update={"params": params}), entity_name
