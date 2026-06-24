import pytest

from app.config import settings
from app.models.intent import IntentDocument
from app.schema.loader import reset_schema_catalog
from tools.redis.search.resolve import resolve


@pytest.fixture(autouse=True)
def preprod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setattr(settings, "APP_ENV", "preprod")
    reset_schema_catalog()


def test_resolve_scan_to_get_upgrade():
    intent = IntentDocument(
        backend="redis",
        operation="scan_keys",
        params={"entity": "session", "id": "abcdef01-2345-6789-abcd-ef0123456789"},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "redis session abcdef01-2345-6789-abcd-ef0123456789")
    assert resolved.operation == "get"
    assert resolved.params["key"] == "session:abcdef01-2345-6789-abcd-ef0123456789"
    assert entity == "session"
