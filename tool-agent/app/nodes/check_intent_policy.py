from __future__ import annotations

from app.intent_policy import check_confidence
from app.observability.tracer import tracer
from app.state import ToolAgentState


async def check_intent_policy_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state

    intent = state["intent"]
    request_id = state["request_id"]
    agent_caller = state.get("agent_caller")
    parse_source = state.get("parse_source") or "rules"

    conf_err = check_confidence(intent, agent_caller=agent_caller, parse_source=parse_source)
    if conf_err:
        await tracer.span(
            request_id,
            "intent policy · low confidence",
            output={"error": conf_err},
            level="WARNING",
        )
        return {
            **state,
            "error": conf_err,
            "error_status": 422,
            "intent": intent,
            "parse_source": parse_source,
        }

    return state
