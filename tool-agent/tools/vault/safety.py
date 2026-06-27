from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.models.intent import IntentDocument, SafetyError, ToolsWriteConfirmation
from tools.vault.paths import normalize_vault_path

READ_OPERATIONS = frozenset({"list_secrets", "read_secret", "list_mounts"})
WRITE_OPERATIONS = frozenset({"write_secret", "delete_secret"})


def is_write_operation(operation: str) -> bool:
    return operation in WRITE_OPERATIONS


def _load_allowlists() -> tuple[list[str], list[str]]:
    schema_path = Path(__file__).resolve().parent / "schema" / f"{settings.APP_ENV}.yaml"
    if not schema_path.exists():
        schema_path = Path(__file__).resolve().parent / "schema" / "preprod.yaml"
    if not schema_path.exists():
        return ["data/preprod/"], ["data/preprod/infra/", "data/preprod/services/"]
    with schema_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return list(raw.get("read_allowlist") or []), list(raw.get("write_allowlist") or [])


def _secret_path(intent: IntentDocument) -> str:
    path = str(intent.params.get("path") or "")
    return normalize_vault_path(path)


def _path_allowed(path: str, prefixes: list[str]) -> bool:
    if not path:
        return False
    normalized = path if path.endswith("/") else f"{path}/"
    return any(normalized.startswith(prefix) if prefix.endswith("/") else path.startswith(prefix) for prefix in prefixes)


def validate_path(intent: IntentDocument, *, for_write: bool) -> None:
    path = _secret_path(intent)
    read_allow, write_allow = _load_allowlists()
    prefixes = write_allow if for_write else read_allow
    if not _path_allowed(path, prefixes):
        scope = "write" if for_write else "read"
        raise SafetyError(f"Vault path '{path or '(missing)'}' is not in {scope} allowlist")


def validate(
    intent: IntentDocument,
    *,
    request_read_only: bool,
    write_confirmation: ToolsWriteConfirmation | None = None,
    is_execute_path: bool = False,
) -> None:
    if intent.operation in READ_OPERATIONS:
        if intent.operation == "list_mounts":
            return
        validate_path(intent, for_write=False)
        return

    if intent.operation not in WRITE_OPERATIONS:
        raise SafetyError(f"Unknown or disallowed vault operation '{intent.operation}'")

    if not is_execute_path:
        raise SafetyError(
            f"Vault write operation '{intent.operation}' is blocked on /query — use /plan then /execute"
        )

    if request_read_only or intent.read_only:
        raise SafetyError("Vault write blocked: request is read-only")

    if not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError("Vault writes blocked: TOOL_AGENT_ALLOW_WRITES=false")

    if not settings.VAULT_MCP_WRITES_ENABLED:
        raise SafetyError("Vault writes blocked: VAULT_MCP_WRITES_ENABLED=false")

    validate_path(intent, for_write=True)

    if write_confirmation is None:
        raise SafetyError(
            "Vault write requires write_confirmation from /plan (confirmation_token + confirmation_phrase)"
        )

    from app.vault_write_confirm import verify_write_confirmation

    if not verify_write_confirmation(
        write_confirmation.confirmation_token,
        write_confirmation.confirmation_phrase,
        intent,
    ):
        raise SafetyError("Invalid or expired vault write confirmation")


def validate_tool_params(operation: str, params: dict[str, Any]) -> None:
    if operation in READ_OPERATIONS | WRITE_OPERATIONS:
        if operation != "list_mounts" and not (params.get("path") or params.get("entity")):
            raise SafetyError(f"vault.{operation} requires params.path or params.entity")
        return
    raise SafetyError(f"Vault operation '{operation}' is not allowed")
