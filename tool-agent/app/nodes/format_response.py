from __future__ import annotations

from app.config import settings
from app.llm_client import get_llm_client
from app.observability.tracer import tracer
from app.observability.usage import LlmUsageRecord, UsageLedger
from app.state import ToolAgentState


async def format_response_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state

    response = state.get("response")
    request = state["request"]
    if not response or not request.include_summary:
        return state

    if not settings.LLM_SUMMARY_ENABLED:
        return state

    llm = get_llm_client()
    if not llm.available:
        return state

    ledger: UsageLedger = state.get("usage_ledger") or UsageLedger()
    user = (
        f"Summarize this {response.backend}.{response.operation} result for an operator.\n"
        f"Data preview: {str(response.data)[:4000]}"
    )
    summary_result = None
    try:
        summary_result = await llm.chat_with_usage(
            system="You summarize infra tool query results briefly in plain English.",
            user=user,
            request_id=state["request_id"],
            backend=response.backend,
            generation_name="tool-agent-summary",
        )
        ledger.add_llm(
            LlmUsageRecord(
                name="format_response",
                model=summary_result.model,
                prompt_tokens=summary_result.usage.get("prompt_tokens", 0),
                completion_tokens=summary_result.usage.get("completion_tokens", 0),
                total_tokens=summary_result.usage.get("total_tokens", 0),
                latency_ms=summary_result.latency_ms,
            )
        )
        response.summary = summary_result.content.strip()
    except Exception:
        return state

    span_metadata: dict[str, object] = {"step": "format_response"}
    if summary_result.gateway_trace_id:
        span_metadata["gateway_trace_id"] = summary_result.gateway_trace_id
    span_id = await tracer.span(
        state["request_id"],
        "format response · summary",
        input={"backend": response.backend, "operation": response.operation},
        output={"summary": response.summary},
        metadata=span_metadata,
    )
    if llm.routing == "direct":
        await tracer.generation(
            state["request_id"],
            "tool-agent-summary",
            model=summary_result.model,
            input=user,
            output=summary_result.content,
            usage=summary_result.usage,
            cost_usd=summary_result.cost_usd,
            latency_ms=summary_result.latency_ms,
            parent_observation_id=span_id,
            metadata={"step": "format_response", "source_name": "litellm/direct"},
        )

    return {**state, "response": response, "usage_ledger": ledger}
