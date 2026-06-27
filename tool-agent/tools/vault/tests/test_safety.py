import pytest

from app.config import settings
from app.models.intent import IntentDocument, SafetyError, ToolsWriteConfirmation
from app.vault_write_confirm import clear_store, issue_write_confirmation
from tools.vault.safety import validate


@pytest.fixture(autouse=True)
def _reset_confirm_store():
    clear_store()
    yield
    clear_store()


def _read_intent(path: str = "data/preprod/infra/postgres") -> IntentDocument:
    return IntentDocument(
        backend="vault",
        operation="read_secret",
        params={"path": path, "mount": "apps"},
        confidence=0.9,
        rationale="test",
    )


def _write_intent(path: str = "data/preprod/infra/postgres") -> IntentDocument:
    return IntentDocument(
        backend="vault",
        operation="write_secret",
        params={"path": path, "mount": "apps", "key": "test", "value": "x"},
        read_only=False,
        confidence=0.9,
        rationale="test",
    )


def test_list_mounts_skips_path_allowlist():
    validate(
        IntentDocument(
            backend="vault",
            operation="list_mounts",
            params={},
            confidence=0.9,
            rationale="test",
        ),
        request_read_only=True,
        is_execute_path=False,
    )


def test_write_blocked_on_query():
    with pytest.raises(SafetyError, match="/query"):
        validate(_write_intent(), request_read_only=False, is_execute_path=False)


def test_write_requires_confirmation_on_execute(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_AGENT_ALLOW_WRITES", True)
    monkeypatch.setattr(settings, "VAULT_MCP_WRITES_ENABLED", True)
    with pytest.raises(SafetyError, match="write_confirmation"):
        validate(_write_intent(), request_read_only=False, is_execute_path=True)


def test_write_succeeds_with_valid_confirmation(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_AGENT_ALLOW_WRITES", True)
    monkeypatch.setattr(settings, "VAULT_MCP_WRITES_ENABLED", True)
    intent = _write_intent()
    token, phrase = issue_write_confirmation(intent)
    validate(
        intent,
        request_read_only=False,
        is_execute_path=True,
        write_confirmation=ToolsWriteConfirmation(
            confirmation_token=token,
            confirmation_phrase=phrase,
        ),
    )


def test_path_not_in_allowlist():
    with pytest.raises(SafetyError, match="allowlist"):
        validate(
            _read_intent("data/prod/infra/postgres"),
            request_read_only=True,
            is_execute_path=False,
        )
