from __future__ import annotations

import pytest

from app.intent_schema import IntentDocument
from app.resolve_params import (
    ParamResolutionError,
    extract_email,
    extract_uuid,
    infer_entity_from_text,
    resolve_intent_params,
)
from app.schema_catalog import reset_schema_catalog


@pytest.fixture(autouse=True)
def _reset_catalog():
    reset_schema_catalog()
    yield
    reset_schema_catalog()


def test_extract_uuid():
    text = "portfolio 163d0143-4fcb-480c-ac20-622f14e0e293 details"
    assert extract_uuid(text) == "163d0143-4fcb-480c-ac20-622f14e0e293"


def test_infer_entity_from_text():
    assert infer_entity_from_text("find user by id") == "user"
    assert infer_entity_from_text("find user by id", backend="postgres") == "user_account"
    assert infer_entity_from_text("portfolio lookup") == "portfolio"
    assert infer_entity_from_text("portfolio lookup", backend="postgres") == "portfolio_pg"
    assert infer_entity_from_text("redis session keys", backend="redis") == "session"
    assert infer_entity_from_text("search bug_memory collection") == "bug_memory"


def test_extract_email():
    assert extract_email("find user details of email ssd2658@gmail.com") == "ssd2658@gmail.com"


def test_resolve_user_account_by_email():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={
            "entity": "user_account",
            "lookup_field": "email",
            "lookup_value": "ssd2658@gmail.com",
        },
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "user_account"
    assert "user_accounts" in resolved.params["sql"]
    assert "ssd2658@gmail.com" in resolved.params["sql"]
    assert "email" in resolved.params["sql"]


def test_resolve_mongo_user_by_email():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={
            "entity": "user",
            "lookup_field": "email",
            "lookup_value": "ssd2658@gmail.com",
        },
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "user"
    assert resolved.params["filter"] == {"email": "ssd2658@gmail.com"}
    assert resolved.params["collection"] == "users"


def test_rule_postgres_user_email():
    from app.nodes.parse_intent import _rule_based_intent

    intent = _rule_based_intent(
        "find user details of email ssd2658@gmail.com",
        "postgres",
    )
    assert intent is not None
    assert intent.operation == "run_sql"
    assert intent.params["entity"] == "user_account"
    assert intent.params["lookup_value"] == "ssd2658@gmail.com"


def test_resolve_postgres_entity_id():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={"entity": "portfolio_pg", "id": "163d0143-4fcb-480c-ac20-622f14e0e293"},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "portfolio_pg"
    assert "SELECT * FROM" in resolved.params["sql"]
    assert "portfolios" in resolved.params["sql"]
    assert resolved.params["schema"] == "public"


def test_resolve_redis_session_entity():
    intent = IntentDocument(
        backend="redis",
        operation="get",
        params={"entity": "session", "id": "abc-123"},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "session"
    assert resolved.params["key"] == "session:abc-123"


def test_resolve_redis_scan_session_pattern():
    intent = IntentDocument(
        backend="redis",
        operation="scan_keys",
        params={"entity": "session"},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "session"
    assert resolved.params["pattern"] == "session:*"


def test_resolve_postgres_table_count_entity():
    intent = IntentDocument(
        backend="postgres",
        operation="table_row_count",
        params={"entity": "portfolio_pg"},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert resolved.params["table"] == "portfolios"
    assert resolved.params["schema"] == "public"


def test_resolve_entity_portfolio_id():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={
            "entity": "portfolio",
            "id": "163d0143-4fcb-480c-ac20-622f14e0e293",
        },
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "portfolio"
    assert resolved.params["database"] == "portfolio"
    assert resolved.params["collection"] == "portfolios"
    assert resolved.params["filter"] == {"_id": "163d0143-4fcb-480c-ac20-622f14e0e293"}


def test_resolve_filter_id_without_collection():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={"filter": {"_id": "163d0143-4fcb-480c-ac20-622f14e0e293"}},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(
        intent,
        query_text="get portfolio 163d0143-4fcb-480c-ac20-622f14e0e293",
    )
    assert resolved.params["database"] == "portfolio"
    assert resolved.params["collection"] == "portfolios"
    assert entity == "portfolio"


def test_resolve_missing_params_raises():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={"filter": {}},
        confidence=1.0,
        rationale="test",
    )
    with pytest.raises(ParamResolutionError, match="Missing database/collection"):
        resolve_intent_params(intent)


def test_resolve_qdrant_entity():
    intent = IntentDocument(
        backend="qdrant",
        operation="scroll",
        params={"entity": "bug_memory", "limit": 5},
        confidence=1.0,
        rationale="test",
    )
    resolved, entity = resolve_intent_params(intent)
    assert entity == "bug_memory"
    assert resolved.params["collection"] == "bug_memory"


def test_rule_mongo_find_with_uuid():
    from app.nodes.parse_intent import _rule_based_intent

    intent = _rule_based_intent(
        "find portfolio 163d0143-4fcb-480c-ac20-622f14e0e293",
        "mongodb",
    )
    assert intent is not None
    assert intent.operation == "find"
    assert intent.params["database"] == "portfolio"
    assert intent.params["collection"] == "portfolios"
    assert intent.params["filter"]["_id"] == "163d0143-4fcb-480c-ac20-622f14e0e293"
