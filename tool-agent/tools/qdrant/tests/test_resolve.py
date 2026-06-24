import pytest

from app.config import settings
from app.models.intent import IntentDocument
from app.schema.loader import reset_schema_catalog
from tools.qdrant.search.resolve import resolve


@pytest.fixture(autouse=True)
def preprod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setattr(settings, "APP_ENV", "preprod")
    reset_schema_catalog()


def test_resolve_bug_memory_collection():
    intent = IntentDocument(
        backend="qdrant",
        operation="collection_info",
        params={},
        read_only=True,
        confidence=1.0,
    )
    resolved, entity = resolve(intent, "qdrant bug_memory points")
    assert resolved.params["collection"] == "bug_memory"
    assert entity == "bug_memory"
