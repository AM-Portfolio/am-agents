from app.models.intent import IntentDocument
from tools._shared.resolve import resolve_intent_params
from tools.vault.search.fuzzy import resolve_vault_target, target_to_params


def test_vault_am_analysis_entity_resolves_path():
    query = "read secret preprod am-analysis services"
    target = resolve_vault_target(query)
    params = target_to_params(target)
    intent = IntentDocument(
        backend="vault",
        operation="read_secret",
        params=params,
        read_only=True,
        confidence=0.9,
    )
    resolved, entity = resolve_intent_params(intent, query_text=query)
    assert resolved.params["path"] == "preprod/services/am-analysis"
    assert entity is None


def test_vault_am_analysis_entity_only_from_llm():
    intent = IntentDocument(
        backend="vault",
        operation="read_secret",
        params={"entity": "am_analysis"},
        read_only=True,
        confidence=0.85,
    )
    resolved, entity = resolve_intent_params(
        intent, query_text="read secret preprod am-analysis services"
    )
    assert resolved.params["path"] == "preprod/services/am-analysis"
    assert entity is None
