from __future__ import annotations

from app.models.intent import IntentDocument
from app.observability.tracer import tracer
from app.state import ToolAgentState
from tools._loader import get_tool
from tools._shared.intent_trace import clear_resolve_trace, get_resolve_trace, merge_trace_metadata
from tools._shared.resolve import ParamResolutionError, resolve_intent_params


async def resolve_params_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state

    intent: IntentDocument = state["intent"]
    request_id = state["request_id"]
    query = state["request"].query
    if not get_tool(intent.backend):
        return {
            **state,
            "error": f"Unknown backend '{intent.backend}'",
            "error_status": 422,
        }

    tool = get_tool(intent.backend)

    clear_resolve_trace()
    try:
        resolved, entity = resolve_intent_params(intent, query_text=query)
        if tool:
            resolved, tool_entity = tool.resolve(resolved, query)
            entity = entity or tool_entity
    except ParamResolutionError as exc:
        return {**state, "error": exc.message, "error_status": 400}
    except Exception as exc:
        return {**state, "error": str(exc), "error_status": 400}

    trace_meta = merge_trace_metadata(
        {"step": "resolve_params"},
        **get_resolve_trace(),
    )
    await tracer.span(
        request_id,
        f"resolve params · {intent.backend}",
        input={"intent": intent.model_dump()},
        output={"params": resolved.params, "entity": entity},
        metadata=trace_meta,
    )
    return {
        **state,
        "intent": resolved,
        "resolved_params": resolved.params,
        "entity": entity,
    }
