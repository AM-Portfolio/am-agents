from __future__ import annotations

from app.models.intent import SafetyError
from app.observability.tracer import tracer
from app.safety import validate_intent
from app.state import ToolAgentState


async def validate_safety_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state
    intent = state["intent"]
    request = state["request"]
    request_id = state["request_id"]
    try:
        validate_intent(
            intent,
            request_read_only=request.read_only,
            write_confirmation=state.get("write_confirmation"),
            is_execute_path=state.get("parse_source") == "structured",
        )
    except SafetyError as exc:
        await tracer.span(
            request_id,
            f"safety blocked · {intent.backend}.{intent.operation}",
            output={"error": exc.message},
            level="WARNING",
        )
        return {**state, "error": exc.message, "error_status": 403}
    await tracer.span(request_id, f"safety passed · {intent.backend}.{intent.operation}")
    return state
