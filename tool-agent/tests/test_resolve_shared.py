from app.models.intent import IntentDocument
from tools._shared.resolve import resolve_intent_params


def test_mongo_portfolio_entity_resolve():
    pid = "163d0143-4fcb-480c-ac20-622f14e0e293"
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={"entity": "portfolio", "id": pid},
        read_only=True,
        confidence=0.9,
    )
    resolved, entity = resolve_intent_params(intent, query_text=f"find portfolio {pid}")
    assert entity == "portfolio"
    assert resolved.params.get("database") == "portfolio"
    assert resolved.params.get("collection") == "portfolios"
    assert resolved.params.get("filter", {}).get("_id") == pid


def test_redis_session_key_resolve():
    uid = "11111111-1111-1111-1111-111111111111"
    intent = IntentDocument(
        backend="redis",
        operation="get",
        params={"entity": "session", "id": uid},
        read_only=True,
        confidence=0.9,
    )
    resolved, entity = resolve_intent_params(intent, query_text=f"get session {uid}")
    assert entity == "session"
    assert resolved.params.get("key") == f"session:{uid}"
