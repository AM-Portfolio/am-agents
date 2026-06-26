import pytest

from app.config import settings
from app.models.intent import IntentDocument
from app.schema.loader import reset_schema_catalog
from tools.postgres.search.resolve import resolve


@pytest.fixture(autouse=True)
def preprod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setattr(settings, "APP_ENV", "preprod")
    reset_schema_catalog()


def test_resolve_table_row_count_from_entity():
    intent = IntentDocument(
        backend="postgres",
        operation="table_row_count",
        params={"entity": "portfolio_pg"},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "how many portfolios in postgres")
    assert entity == "portfolio_pg"
    assert resolved.params["table"] == "portfolios"
    assert resolved.params["schema"] == "public"


def test_resolve_user_email_sql():
    intent = IntentDocument(
        backend="postgres",
        operation="run_sql",
        params={
            "entity": "user_account",
            "lookup_field": "email",
            "lookup_value": "test@example.com",
        },
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "find postgres user test@example.com")
    assert entity == "user_account"
    assert "user_accounts" in resolved.params["sql"]
    assert "test@example.com" in resolved.params["sql"]
