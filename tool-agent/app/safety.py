from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError, ToolCall, ToolsWriteConfirmation
from tools._loader import get_tool


def validate_intent(
    intent: IntentDocument,
    *,
    request_read_only: bool,
    write_confirmation: ToolsWriteConfirmation | None = None,
    is_execute_path: bool = False,
) -> None:
    tool = get_tool(intent.backend)
    if not tool:
        raise SafetyError(f"Unknown or disabled backend '{intent.backend}'")
    tool.validate_intent(intent)
    if intent.backend == "vault":
        from tools.vault.safety import validate as validate_vault_safety

        validate_vault_safety(
            intent,
            request_read_only=request_read_only,
            write_confirmation=write_confirmation,
            is_execute_path=is_execute_path,
        )
        return
    tool.validate_safety(intent, request_read_only=request_read_only)


def validate_tool_call(tool_call: ToolCall) -> None:
    if settings.TOOL_AGENT_ALLOW_WRITES and not settings.TOOL_AGENT_READ_ONLY_DEFAULT:
        return
    if not tool_call.read_only:
        raise SafetyError("Tool call is not marked read_only")
