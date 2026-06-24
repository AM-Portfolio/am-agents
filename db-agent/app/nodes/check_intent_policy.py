from __future__ import annotations

from app.intent_policy import check_confidence
from app.observability.tracer import tracer
from app.state import DbAgentState


async def check_intent_policy_node(state: DbAgentState) -> DbAgentState:
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
            input={"confidence": intent.confidence, "agent_caller": agent_caller},
            output={"status": "error", "message": conf_err},
            metadata={"step": "check_intent_policy"},
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
