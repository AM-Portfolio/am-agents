from __future__ import annotations

from app.intent_schema import SafetyError
from app.observability.tracer import tracer
from app.observability.trace_labels import (
    validate_safety_input,
    validate_safety_output_blocked,
    validate_safety_output_passed,
    validate_safety_span_name,
)
from app.safety import validate_intent
from app.state import DbAgentState


async def validate_safety_node(state: DbAgentState) -> DbAgentState:
    if state.get("error"):
        return state
    intent = state["intent"]
    request = state["request"]
    request_id = state["request_id"]
    span_input = validate_safety_input(intent, request_read_only=request.read_only)
    try:
        validate_intent(intent, request_read_only=request.read_only)
    except SafetyError as exc:
        await tracer.span(
            request_id,
            validate_safety_span_name(intent),
            input=span_input,
            output=validate_safety_output_blocked(exc.message),
            metadata={"step": "validate_safety", "source_name": "safety-gate/layer-2"},
            level="WARNING",
        )
        return {**state, "error": exc.message, "error_status": 403}
    await tracer.span(
        request_id,
        validate_safety_span_name(intent),
        input=span_input,
        output=validate_safety_output_passed(intent),
        metadata={"step": "validate_safety", "source_name": "safety-gate/layer-2"},
    )
    return state
