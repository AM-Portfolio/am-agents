from __future__ import annotations

from app.config import settings
from app.llm_client import get_llm_client
from app.observability.tracer import tracer
from app.observability.usage import LlmUsageRecord, UsageLedger
from app.prompts.builder import build_summary_prompt
from app.state import ToolAgentState
from app.stream_context import emit_stream, is_streaming_active
from tools._shared.god_mode import strip_god_mode


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
    _, god_mode = strip_god_mode(request.query.strip())
    god_mode = bool(state.get("god_mode") or god_mode)
    data_preview = str(response.data)[:8000 if god_mode else 4000]
    system, user = build_summary_prompt(
        backend=response.backend,
        operation=response.operation,
        query=request.query.strip(),
        data_preview=data_preview,
        god_mode=god_mode,
    )
    summary_result = None
    try:
        if is_streaming_active() and llm.routing == "direct":
            async def _on_token(token: str) -> None:
                await emit_stream("token", {"stage": "summary", "text": token})

            summary_result = await llm.chat_stream_with_usage(
                system=system,
                user=user,
                request_id=state["request_id"],
                backend=response.backend,
                generation_name="tool-agent-summary",
                on_token=_on_token,
            )
        else:
            summary_result = await llm.chat_with_usage(
                system=system,
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
    if god_mode:
        span_metadata["god_mode"] = True
    if summary_result.gateway_trace_id:
        span_metadata["gateway_trace_id"] = summary_result.gateway_trace_id
    span_id = await tracer.span(
        state["request_id"],
        "format response · summary",
        input={"backend": response.backend, "operation": response.operation, "god_mode": god_mode},
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
