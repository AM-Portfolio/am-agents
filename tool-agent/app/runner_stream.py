from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
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
from app.models.stream_events import sse_line, stage_event
from app.nodes.check_intent_policy import check_intent_policy_node
from app.nodes.execute_tool import resolve_and_execute_node
from app.nodes.format_response import format_response_node
from app.nodes.parse_intent import parse_intent_node
from app.nodes.resolve_params import resolve_params_node
from app.nodes.validate_safety import validate_safety_node
from app.observability.tracer import tracer
from app.observability.trace_labels import trace_metadata
from app.runner import _base_state, _finalize_query_result, _trace_context_from_result, _trace_context_from_state
from app.stream_context import set_stream_emit, set_streaming_active
from app.vault_write_confirm import issue_write_confirmation
from tools._shared.intent_trace import get_resolve_trace
from tools._shared.resolve import ParamResolutionError
from tools.vault.safety import is_write_operation

logger = logging.getLogger(__name__)

_PLAN_NODES: tuple[tuple[str, Any], ...] = (
    ("parse_intent", parse_intent_node),
    ("resolve_params", resolve_params_node),
    ("validate_safety", validate_safety_node),
    ("check_intent_policy", check_intent_policy_node),
)

_EXECUTE_NODES: tuple[tuple[str, Any], ...] = (
    ("resolve_params", resolve_params_node),
    ("validate_safety", validate_safety_node),
    ("check_intent_policy", check_intent_policy_node),
    ("execute_tool", resolve_and_execute_node),
    ("format_response", format_response_node),
)


def _merge_state(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(state)
    merged.update(update)
    return merged


def _node_payload(stage: str, state: dict[str, Any]) -> dict[str, Any]:
    if stage == "parse_intent" and state.get("intent"):
        intent = state["intent"]
        return {
            "backend": intent.backend,
            "operation": intent.operation,
            "confidence": intent.confidence,
            "parse_source": state.get("parse_source"),
        }
    if stage == "resolve_params":
        intent = state.get("intent")
        payload = dict(get_resolve_trace())
        if intent:
            payload["params"] = intent.params
        if state.get("entity"):
            payload["entity"] = state["entity"]
        return payload
    if stage == "execute_tool" and state.get("response"):
        resp = state["response"]
        return {
            "backend": resp.backend,
            "operation": resp.operation,
            "tool_source": resp.tool_source,
            "duration_ms": resp.duration_ms,
        }
    return {}


async def _run_nodes_with_events(
    state: dict[str, Any],
    nodes: tuple[tuple[str, Any], ...],
    queue: asyncio.Queue[str | None],
) -> dict[str, Any]:
    current = dict(state)
    for stage, node_fn in nodes:
        started = time.perf_counter()
        await queue.put(stage_event(stage, "started"))
        current = await node_fn(current)
        ms = int((time.perf_counter() - started) * 1000)
        if current.get("error"):
            await queue.put(
                stage_event(stage, "failed", data={"error": current["error"]}, ms=ms)
            )
            await queue.put(
                sse_line(
                    event="error",
                    data={
                        "message": current["error"],
                        "status": current.get("error_status", 500),
                        "stage": stage,
                    },
                )
            )
            return current
        payload = _node_payload(stage, current)
        if stage == "parse_intent" and payload:
            await queue.put(sse_line(event="intent", data=payload))
        if stage == "resolve_params" and payload:
            await queue.put(sse_line(event="resolved", data=payload))
        if stage == "validate_safety":
            await queue.put(sse_line(event="safety", data={"ok": True}))
        if stage == "execute_tool" and current.get("response"):
            resp: ToolsQueryResponse = current["response"]
            preview = str(resp.data)[:2000]
            await queue.put(sse_line(event="result", data={"preview": preview, **payload}))
        await queue.put(stage_event(stage, "completed", data=payload or None, ms=ms))
    return current


async def _stream_worker(
    queue: asyncio.Queue[str | None],
    coro,
) -> None:
    try:
        await coro
    except Exception as exc:
        logger.exception("stream worker failed")
        await queue.put(sse_line(event="error", data={"message": str(exc), "status": 500}))
    finally:
        await queue.put(None)


async def _iter_queue(queue: asyncio.Queue[str | None]) -> AsyncIterator[str]:
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def stream_tools_query(
    request: ToolsQueryRequest,
    *,
    agent_caller: str | None = None,
) -> AsyncIterator[str]:
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        yield sse_line(event="error", data={"message": "Streaming disabled", "status": 503})
        return

    agent_err = check_agent_requirements(request, agent_caller=agent_caller)
    if agent_err:
        yield sse_line(event="error", data={"message": agent_err, "status": 400})
        return

    request_id = str(uuid.uuid4())
    state = _base_state(request_id=request_id, request=request, agent_caller=agent_caller)
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put(sse_line(event=event, data=data))  # type: ignore[arg-type]

    set_stream_emit(emit)
    set_streaming_active(True)

    await tracer.start_trace(
        request_id,
        query=request.query,
        metadata=trace_metadata(
            backend_hint=request.backend,
            agent_caller=agent_caller,
            extra={"description": "tool-agent query stream"},
        ),
    )

    async def run() -> None:
        try:
            current = dict(state)
            async for chunk in tool_agent_graph.astream(state, stream_mode="updates"):
                for stage, update in chunk.items():
                    current = _merge_state(current, update)
                    if update.get("error"):
                        await queue.put(stage_event(stage, "failed", data={"error": update["error"]}))
                        await queue.put(
                            sse_line(
                                event="error",
                                data={
                                    "message": update["error"],
                                    "status": update.get("error_status", 500),
                                    "stage": stage,
                                },
                            )
                        )
                        await tracer.end_trace(
                            request_id, error=str(update["error"]), **_trace_context_from_result(current)
                        )
                        return
                    payload = _node_payload(stage, current)
                    if stage == "parse_intent" and payload:
                        await queue.put(sse_line(event="intent", data=payload))
                    if stage == "resolve_params" and payload:
                        await queue.put(sse_line(event="resolved", data=payload))
                    if stage == "execute_tool" and current.get("response"):
                        resp: ToolsQueryResponse = current["response"]
                        await queue.put(
                            sse_line(
                                event="result",
                                data={
                                    "preview": str(resp.data)[:2000],
                                    "backend": resp.backend,
                                    "operation": resp.operation,
                                },
                            )
                        )
                    await queue.put(stage_event(stage, "completed", data=payload or None))
            if current.get("response"):
                result = await _finalize_query_result(request_id, current)
                response: ToolsQueryResponse = result["response"]
                await queue.put(sse_line(event="done", data={"response": response.model_dump()}))
            elif current.get("error"):
                await tracer.end_trace(request_id, error=current["error"])
            else:
                await tracer.end_trace(request_id, error="No response produced")
                await queue.put(
                    sse_line(event="error", data={"message": "No response produced", "status": 500})
                )
        except Exception as exc:
            logger.exception("query stream failed")
            await tracer.end_trace(request_id, error=str(exc))
            await queue.put(sse_line(event="error", data={"message": str(exc), "status": 500}))
        finally:
            set_stream_emit(None)
            set_streaming_active(False)

    worker = asyncio.create_task(_stream_worker(queue, run()))
    try:
        async for line in _iter_queue(queue):
            yield line
    finally:
        await worker


async def stream_tools_plan(
    request: ToolsPlanRequest,
    *,
    agent_caller: str | None = None,
) -> AsyncIterator[str]:
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        yield sse_line(event="error", data={"message": "Streaming disabled", "status": 503})
        return

    query_request = ToolsQueryRequest(
        query=request.query,
        backend=request.backend,
        read_only=request.read_only,
        include_summary=False,
    )
    agent_err = check_agent_requirements(query_request, agent_caller=agent_caller)
    if agent_err:
        yield sse_line(event="error", data={"message": agent_err, "status": 400})
        return

    request_id = str(uuid.uuid4())
    state = _base_state(request_id=request_id, request=query_request, agent_caller=agent_caller)
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def run() -> None:
        await tracer.start_trace(
            request_id, query=request.query, metadata=trace_metadata(backend_hint=request.backend)
        )
        current = await _run_nodes_with_events(state, _PLAN_NODES, queue)
        if current.get("error"):
            await tracer.end_trace(request_id, error=current["error"], **_trace_context_from_state(current))
            return
        intent = current["intent"]
        parse_source = current.get("parse_source") or "rules"
        plan = ToolsPlanResponse(
            request_id=request_id,
            intent=intent,
            would_execute=would_execute_label(intent),
            confidence_ok=intent.confidence >= settings.TOOL_AGENT_INTENT_MIN_CONFIDENCE,
            parse_source=parse_source,
            min_confidence=settings.TOOL_AGENT_INTENT_MIN_CONFIDENCE,
        )
        if intent.backend == "vault" and is_write_operation(intent.operation):
            token, phrase = issue_write_confirmation(intent)
            plan.requires_write_confirmation = True
            plan.confirmation_token = token
            plan.confirmation_phrase = phrase
        await tracer.end_trace(request_id, output=plan.model_dump(), **_trace_context_from_state(current))
        await queue.put(sse_line(event="done", data={"plan": plan.model_dump()}))

    worker = asyncio.create_task(_stream_worker(queue, run()))
    try:
        async for line in _iter_queue(queue):
            yield line
    finally:
        await worker


async def stream_tools_execute(
    request: ToolsExecuteRequest,
    *,
    agent_caller: str | None = None,
) -> AsyncIterator[str]:
    if not settings.TOOL_AGENT_STREAMING_ENABLED:
        yield sse_line(event="error", data={"message": "Streaming disabled", "status": 503})
        return

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
    state["write_confirmation"] = request.write_confirmation
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    set_streaming_active(True)

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put(sse_line(event=event, data=data))  # type: ignore[arg-type]

    set_stream_emit(emit)

    async def run() -> None:
        await tracer.start_trace(
            request_id,
            query=query_request.query,
            metadata=trace_metadata(
                backend=request.intent.backend, operation=request.intent.operation
            ),
        )
        try:
            current = await _run_nodes_with_events(state, _EXECUTE_NODES, queue)
        except ParamResolutionError as exc:
            await tracer.end_trace(request_id, error=exc.message)
            await queue.put(sse_line(event="error", data={"message": exc.message, "status": 400}))
            return
        finally:
            set_stream_emit(None)
            set_streaming_active(False)
        if current.get("error"):
            await tracer.end_trace(request_id, error=current["error"], **_trace_context_from_state(current))
            return
        if current.get("response"):
            result = await _finalize_query_result(request_id, current)
            response: ToolsQueryResponse = result["response"]
            await queue.put(sse_line(event="done", data={"response": response.model_dump()}))
        else:
            await queue.put(
                sse_line(event="error", data={"message": "No response produced", "status": 500})
            )

    worker = asyncio.create_task(_stream_worker(queue, run()))
    try:
        async for line in _iter_queue(queue):
            yield line
    finally:
        await worker
