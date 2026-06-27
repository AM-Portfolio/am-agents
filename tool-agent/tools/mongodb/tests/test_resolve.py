import pytest

from app.config import settings
from app.models.intent import IntentDocument
from app.schema.loader import reset_schema_catalog
from tools.mongodb.search.resolve import resolve


@pytest.fixture(autouse=True)
def preprod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setattr(settings, "APP_ENV", "preprod")
    reset_schema_catalog()


def test_resolve_fills_default_database_for_list_collections():
    intent = IntentDocument(
        backend="mongodb",
        operation="list_collections",
        params={},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "list portfolio collections")
    assert resolved.params.get("database") == "portfolio"
    assert entity is None


def test_resolve_entity_portfolio_find():
    intent = IntentDocument(
        backend="mongodb",
        operation="find",
        params={"entity": "portfolio", "id": "abcdef01-2345-6789-abcd-ef0123456789"},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "find portfolio abcdef01-2345-6789-abcd-ef0123456789")
    assert entity == "portfolio"
    assert resolved.params["database"] == "portfolio"
    assert resolved.params["collection"] == "portfolios"
    assert resolved.params["filter"]["_id"] == "abcdef01-2345-6789-abcd-ef0123456789"
