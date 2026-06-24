from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.config import settings
from app.graph import tool_agent_graph
from app.intent_policy import check_agent_requirements, would_execute_label
from app.models.intent import (
    ToolsExecuteRequest,
    ToolsPlanRequest,
    ToolsPlanResponse,
    ToolsQueryRequest,
    ToolsQueryResponse,
)
from app.nodes.execute_tool import resolve_and_execute_node
from app.nodes.format_response import format_response_node
from app.nodes.parse_intent import parse_intent_node
from app.nodes.resolve_params import resolve_params_node
from app.nodes.validate_safety import validate_safety_node
from app.observability.tracer import tracer
from app.observability.trace_labels import tool_fqn, trace_metadata
from app.observability.usage import UsageLedger
from tools._shared.resolve import ParamResolutionError

logger = logging.getLogger(__name__)


def _trace_context_from_state(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent")
    if not intent:
        return {}
    return {
        "backend": intent.backend,
        "operation": intent.operation,
        "parse_source": state.get("parse_source"),
        "agent_caller": state.get("agent_caller"),
    }


def _trace_context_from_result(result: dict[str, Any]) -> dict[str, Any]:
    ctx = _trace_context_from_state(result)
    intent_raw = result.get("intent")
    if intent_raw and not ctx.get("backend"):
        if hasattr(intent_raw, "backend"):
            ctx["backend"] = intent_raw.backend
            ctx["operation"] = intent_raw.operation
        elif isinstance(intent_raw, dict):
            ctx["backend"] = intent_raw.get("backend")
            ctx["operation"] = intent_raw.get("operation")
    if result.get("parse_source") and not ctx.get("parse_source"):
        ctx["parse_source"] = result.get("parse_source")
    return ctx


def _base_state(*, request_id: str, request: ToolsQueryRequest, agent_caller: str | None = None) -> dict[str, Any]:
    return {
        "request": request,
        "request_id": request_id,
        "max_rows": min(request.max_rows, settings.TOOL_AGENT_MAX_ROWS),
        "started_ms": int(time.time() * 1000),
        "usage_ledger": UsageLedger(),
        "agent_caller": agent_caller,
        "gateway_trace_id": None,
        "parse_source": "rules",
    }


async def run_tools_query(request: ToolsQueryRequest, *, agent_caller: str | None = None) -> dict[str, Any]:
    agent_err = check_agent_requirements(request, agent_caller=agent_caller)
    if agent_err:
        return {"error": agent_err, "status": 400}

    request_id = str(uuid.uuid4())
    state = _base_state(request_id=request_id, request=request, agent_caller=agent_caller)

    await tracer.start_trace(
        request_id,
        query=request.query,
        metadata=trace_metadata(
            backend_hint=request.backend,
            agent_caller=agent_caller,
            extra={"description": "tool-agent query: intent → safety → tool → response"},
        ),
    )

    try:
        result = await tool_agent_graph.ainvoke(state)
    except Exception as exc:
        logger.exception("tool-agent graph failed")
        await tracer.end_trace(request_id, error=str(exc))
        return {"error": str(exc), "status": 500, "request_id": request_id}

    if result.get("error"):
        status = result.get("error_status", 500)
        payload: dict[str, Any] = {"error": result["error"], "status": status, "request_id": request_id}
        if status == 422 and result.get("intent"):
            payload["intent"] = result["intent"].model_dump()
            payload["parse_source"] = result.get("parse_source")
        await tracer.end_trace(request_id, error=result["error"], **_trace_context_from_result(result))
        return payload

    return await _finalize_query_result(request_id, result)


async def run_tools_plan(request: ToolsPlanRequest, *, agent_caller: str | None = None) -> dict[str, Any]:
    query_request = ToolsQueryRequest(
        query=request.query,
        backend=request.backend,
        read_only=request.read_only,
        include_summary=False,
    )
    agent_err = check_agent_requirements(query_request, agent_caller=agent_caller)
    if agent_err:
        return {"error": agent_err, "status": 400}

    request_id = str(uuid.uuid4())
    state = _base_state(request_id=request_id, request=query_request, agent_caller=agent_caller)

    await tracer.start_trace(request_id, query=request.query, metadata=trace_metadata(backend_hint=request.backend))

    state = await parse_intent_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 400), "request_id": request_id}

    state = await resolve_params_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 400), "request_id": request_id}

    state = await validate_safety_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 403), "request_id": request_id}

    intent = state["intent"]
    parse_source = state.get("parse_source") or "rules"
    plan = ToolsPlanResponse(
        request_id=request_id,
        intent=intent,
        would_execute=would_execute_label(intent),
        confidence_ok=intent.confidence >= settings.TOOL_AGENT_INTENT_MIN_CONFIDENCE,
        parse_source=parse_source,
        min_confidence=settings.TOOL_AGENT_INTENT_MIN_CONFIDENCE,
    )
    await tracer.end_trace(
        request_id,
        output=plan.model_dump(),
        **_trace_context_from_state(state),
    )
    return {"plan": plan, "status": 200}


async def run_tools_execute(request: ToolsExecuteRequest, *, agent_caller: str | None = None) -> dict[str, Any]:
    query_request = ToolsQueryRequest(
        query=f"execute {request.intent.backend}.{request.intent.operation}",
        backend=request.intent.backend,
        read_only=request.intent.read_only,
        include_summary=request.include_summary,
        max_rows=request.max_rows,
    )

    request_id = str(uuid.uuid4())
    state = _base_state(request_id=request_id, request=query_request, agent_caller=agent_caller)
    state["intent"] = request.intent.model_copy()
    state["parse_source"] = "structured"

    await tracer.start_trace(
        request_id,
        query=query_request.query,
        metadata=trace_metadata(backend=request.intent.backend, operation=request.intent.operation),
    )

    try:
        state = await resolve_params_node(state)
    except ParamResolutionError as exc:
        await tracer.end_trace(request_id, error=exc.message, **_trace_context_from_state(state))
        return {"error": exc.message, "status": 400, "request_id": request_id}

    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 400), "request_id": request_id}

    state = await validate_safety_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 403), "request_id": request_id}

    state = await resolve_and_execute_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 502), "request_id": request_id}

    state = await format_response_node(state)
    if state.get("error"):
        await tracer.end_trace(request_id, error=state["error"], **_trace_context_from_state(state))
        return {"error": state["error"], "status": state.get("error_status", 500), "request_id": request_id}

    return await _finalize_query_result(request_id, state)


async def _finalize_query_result(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    response: ToolsQueryResponse = result["response"]
    ledger: UsageLedger = result.get("usage_ledger") or UsageLedger()
    await tracer.end_trace(
        request_id,
        output={
            "status": "ok",
            "message": f"Completed {tool_fqn(response.backend, response.operation)} via {response.tool_source}",
            "backend": response.backend,
            "operation": response.operation,
            "usage": ledger.totals(),
        },
        backend=response.backend,
        operation=response.operation,
        parse_source=response.parse_source,
    )
    return {"response": response, "status": 200}
