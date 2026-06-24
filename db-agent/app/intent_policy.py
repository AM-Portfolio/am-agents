from __future__ import annotations

from app.config import settings
from app.intent_schema import DbQueryRequest, IntentDocument, ParseSource
from app.observability.trace_labels import tool_fqn


def is_agent_caller(agent_caller: str | None) -> bool:
    return bool(agent_caller and agent_caller.strip())


def check_agent_requirements(
    request: DbQueryRequest,
    *,
    agent_caller: str | None,
) -> str | None:
    if not is_agent_caller(agent_caller):
        return None
    if settings.DB_AGENT_REQUIRE_BACKEND_FOR_AGENTS and not request.backend:
        return "backend hint is required for agent callers (set backend in request body)"
    return None


def check_confidence(
    intent: IntentDocument,
    *,
    agent_caller: str | None,
    parse_source: ParseSource,
) -> str | None:
    if parse_source == "structured":
        return None
    if not is_agent_caller(agent_caller):
        return None
    if intent.confidence < settings.DB_AGENT_INTENT_MIN_CONFIDENCE:
        return (
            f"Intent confidence {intent.confidence:.2f} below minimum "
            f"{settings.DB_AGENT_INTENT_MIN_CONFIDENCE:.2f}"
        )
    return None


def would_execute_label(intent: IntentDocument) -> str:
    return tool_fqn(intent.backend, intent.operation)
