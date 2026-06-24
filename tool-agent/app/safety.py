from __future__ import annotations

from app.config import settings
from app.models.intent import IntentDocument, SafetyError, ToolCall
from tools._loader import get_tool


def validate_intent(intent: IntentDocument, *, request_read_only: bool) -> None:
    tool = get_tool(intent.backend)
    if not tool:
        raise SafetyError(f"Unknown or disabled backend '{intent.backend}'")
    tool.validate_intent(intent)
    tool.validate_safety(intent, request_read_only=request_read_only)


def validate_tool_call(tool_call: ToolCall) -> None:
    if settings.TOOL_AGENT_ALLOW_WRITES and not settings.TOOL_AGENT_READ_ONLY_DEFAULT:
        return
    if not tool_call.read_only:
        raise SafetyError("Tool call is not marked read_only")
