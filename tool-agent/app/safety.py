from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError, ToolCall, ToolsWriteConfirmation
from tools._loader import get_tool
from tools._shared.capability.approval import requires_write_confirmation, risk_for_operation

CAPABILITY_BACKENDS = frozenset(
    {"work-item", "chat", "mail", "document", "directory", "observe", "spt"}
)


def validate_intent(
    intent: IntentDocument,
    *,
    request_read_only: bool,
    write_confirmation: ToolsWriteConfirmation | None = None,
    is_execute_path: bool = False,
    is_plan_path: bool = False,
    plan_hash: str | None = None,
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
    if intent.backend not in CAPABILITY_BACKENDS:
        return
    risk = risk_for_operation(intent.operation)
    if not requires_write_confirmation(risk):
        return
    if is_plan_path:
        return
    if not is_execute_path:
        raise SafetyError(
            f"{intent.backend}.{intent.operation} is blocked on /query — use /plan then /execute"
        )
    if not write_confirmation:
        raise SafetyError(f"{intent.backend} write requires plan confirmation token")
    from tools._shared.capability.plan_binding import verify_plan_binding

    ok = verify_plan_binding(
        token=write_confirmation.confirmation_token,
        phrase=write_confirmation.confirmation_phrase,
        intent=intent,
        plan_hash=plan_hash,
    )
    if not ok:
        raise SafetyError(f"{intent.backend} write confirmation failed (plan hash / phrase mismatch)")


def validate_tool_call(tool_call: ToolCall) -> None:
    if settings.TOOL_AGENT_ALLOW_WRITES and not settings.TOOL_AGENT_READ_ONLY_DEFAULT:
        return
    if not tool_call.read_only:
        raise SafetyError("Tool call is not marked read_only")
