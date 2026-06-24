from app.models.intent import IntentDocument
from tools._shared.resolve import resolve_intent_params


def test_mongo_user_email_resolve():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={"entity": "user", "lookup_field": "email", "lookup_value": "a@b.com"},
        read_only=True,
        confidence=0.9,
    )
    resolved, entity = resolve_intent_params(intent, query_text="find user by email a@b.com")
    assert entity == "user"
    assert resolved.params.get("collection") == "users"
    assert resolved.params.get("filter", {}).get("email") == "a@b.com"


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
