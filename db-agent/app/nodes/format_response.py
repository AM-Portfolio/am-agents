from __future__ import annotations

import logging
import time

from app.config import settings
from app.intent_schema import DbQueryResponse
from app.llm_client import get_llm_client
from app.observability.tracer import tracer
from app.observability.trace_labels import (
    format_response_input,
    format_response_output,
    format_response_span_name,
    generation_summary_name,
    tool_fqn,
)
from app.observability.usage import LlmUsageRecord, UsageLedger
from app.safety import cap_rows
from app.state import DbAgentState

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = """Summarize database query results for an ops engineer in 2-4 sentences.
Be factual. Mention counts, names, and anomalies. No markdown."""


async def format_response_node(state: DbAgentState) -> DbAgentState:
    if state.get("error"):
        return state

    intent = state["intent"]
    tool_call = state["tool_call"]
    tool_result = state["tool_result"]
    request = state["request"]
    request_id = state["request_id"]
    started = state.get("started_ms") or int(time.time() * 1000)
    max_rows = state.get("max_rows") or request.max_rows

    data, cap_warnings = cap_rows(tool_result.data, max_rows)
    warnings = list(tool_result.warnings) + cap_warnings
    ledger = state.get("usage_ledger") or UsageLedger()

    summary: str | None = None
    summary_result = None
    gateway_trace_id = state.get("gateway_trace_id")
    parse_source = state.get("parse_source") or "rules"
    if request.include_summary and settings.LLM_SUMMARY_ENABLED:
        llm = get_llm_client()
        if llm.available:
            try:
                summary_result = await llm.chat_with_usage(
                    system=_SUMMARY_SYSTEM,
                    user=(
                        f"Query: {request.query}\n"
                        f"Backend: {intent.backend}\n"
                        f"Operation: {intent.operation}\n"
                        f"Data: {str(data)[:4000]}"
                    ),
                    request_id=request_id,
                    backend=intent.backend,
                    generation_name="db-agent-summary",
                )
                summary = summary_result.content
                if summary_result.gateway_trace_id:
                    gateway_trace_id = summary_result.gateway_trace_id
            except Exception as exc:
                logger.warning("Summary LLM failed: %s", exc)
                warnings.append("LLM summary unavailable")

    if summary is None and isinstance(data, dict):
        if "collections" in data:
            names = [c.get("name", c) if isinstance(c, dict) else c for c in data["collections"]]
            summary = f"Found {len(names)} collection(s): {', '.join(str(n) for n in names[:10])}"
        elif "keys" in data:
            summary = f"Found {data.get('count', len(data['keys']))} Redis key(s) matching pattern."

    duration_ms = int(time.time() * 1000) - started
    response = DbQueryResponse(
        request_id=request_id,
        backend=intent.backend,
        operation=intent.operation,
        read_only=intent.read_only,
        confidence=intent.confidence,
        parse_source=parse_source,
        tool_source=tool_result.tool_source,
        tool_name=tool_result.tool_name,
        data=data,
        summary=summary,
        warnings=warnings,
        duration_ms=duration_ms,
        gateway_trace_id=gateway_trace_id,
        resolved_params=intent.params,
        entity=state.get("entity"),
    )
    span_metadata: dict[str, object] = {
        "summary_present": summary is not None,
        "warning_count": len(warnings),
        "duration_ms": duration_ms,
    }
    if summary_result is not None:
        usage_record = LlmUsageRecord(
            name=generation_summary_name(),
            model=summary_result.model,
            prompt_tokens=summary_result.usage.get("prompt_tokens", 0),
            completion_tokens=summary_result.usage.get("completion_tokens", 0),
            total_tokens=summary_result.usage.get("total_tokens", 0),
            cost_usd=summary_result.cost_usd,
            latency_ms=summary_result.latency_ms,
        )
        ledger.add_llm(usage_record)
        span_metadata.update(
            {
                "tokens": usage_record.total_tokens,
                "prompt_tokens": usage_record.prompt_tokens,
                "completion_tokens": usage_record.completion_tokens,
                "cost_usd": usage_record.cost_usd,
            }
        )

    span_id = await tracer.span(
        request_id,
        format_response_span_name(with_llm_summary=summary_result is not None),
        input=format_response_input(
            include_summary=request.include_summary,
            backend=intent.backend,
            operation=intent.operation,
        ),
        output=format_response_output(
            summary=summary,
            warning_count=len(warnings),
            duration_ms=duration_ms,
        ),
        metadata={
            "step": "format_response",
            "source_name": "litellm/direct" if summary_result else "rule-based",
            **span_metadata,
        },
    )

    if summary_result is not None and get_llm_client().routing == "direct":
        await tracer.generation(
            request_id,
            generation_summary_name(),
            model=summary_result.model,
            input=format_response_input(
                include_summary=True,
                backend=intent.backend,
                operation=intent.operation,
            ),
            output=summary_result.content,
            usage=summary_result.usage,
            cost_usd=summary_result.cost_usd,
            latency_ms=summary_result.latency_ms,
            parent_observation_id=span_id,
            metadata={
                "step": "format_response",
                "source_name": "litellm/direct",
                "resolved_tool": tool_fqn(intent.backend, intent.operation),
            },
        )

    return {**state, "response": response, "usage_ledger": ledger}
