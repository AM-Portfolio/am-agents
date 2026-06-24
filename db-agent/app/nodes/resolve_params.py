from __future__ import annotations

from app.intent_schema import IntentDocument
from app.observability.tracer import tracer
from app.resolve_params import ParamResolutionError, resolve_intent_params
from app.state import DbAgentState


async def resolve_params_node(state: DbAgentState) -> DbAgentState:
    if state.get("error"):
        return state

    intent: IntentDocument = state["intent"]
    request_id = state["request_id"]
    query_text = state["request"].query

    try:
        resolved_intent, entity = resolve_intent_params(intent, query_text=query_text)
    except ParamResolutionError as exc:
        await tracer.span(
            request_id,
            "resolve params · failed",
            input={"backend": intent.backend, "operation": intent.operation, "params": intent.params},
            output={"status": "error", "message": exc.message},
            metadata={"step": "resolve_params"},
            level="WARNING",
        )
        return {**state, "error": exc.message, "error_status": 400}

    await tracer.span(
        request_id,
        "resolve params · ok",
        input={"backend": intent.backend, "operation": intent.operation, "params": intent.params},
        output={"params": resolved_intent.params, "entity": entity},
        metadata={"step": "resolve_params"},
    )

    return {
        **state,
        "intent": resolved_intent,
        "resolved_params": resolved_intent.params,
        "entity": entity,
    }
