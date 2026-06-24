from __future__ import annotations

from app.config import settings
from app.llm_client import get_llm_client
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
    try:
        result = await llm.chat_with_usage(
            system="You summarize infra tool query results briefly in plain English.",
            user=user,
            request_id=state["request_id"],
            backend=response.backend,
            generation_name="tool-agent-summary",
        )
        ledger.add_llm(
            LlmUsageRecord(
                name="format_response",
                model=result.model,
                prompt_tokens=result.usage.get("prompt_tokens", 0),
                completion_tokens=result.usage.get("completion_tokens", 0),
                total_tokens=result.usage.get("total_tokens", 0),
                latency_ms=result.latency_ms,
            )
        )
        response.summary = result.content.strip()
    except Exception:
        pass

    return {**state, "response": response, "usage_ledger": ledger}
