from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.llm_client import get_llm_client
from app.models.intent import IntentDocument
from app.observability.tracer import tracer
from app.observability.usage import LlmUsageRecord, UsageLedger
from app.prompts.builder import build_intent_prompt
from app.state import ToolAgentState
from tools._loader import get_enabled_tools, get_tool
from tools._shared.god_mode import strip_god_mode

logger = logging.getLogger(__name__)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _normalize_intent(data: dict[str, Any], backend_hint: str | None) -> IntentDocument:
    backend = str(data.get("backend") or backend_hint or "").strip()
    operation = str(data.get("operation") or "").strip()
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    return IntentDocument(
        backend=backend,
        operation=operation,
        params=params,
        read_only=bool(data.get("read_only", True)),
        confidence=float(data.get("confidence", 0.5)),
        rationale=str(data.get("rationale") or ""),
    )


async def parse_intent_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state

    request = state["request"]
    request_id = state["request_id"]
    raw_query = request.query.strip()
    query, god_mode = strip_god_mode(raw_query)
    backend_hint = request.backend
    state_updates: dict[str, object] = {"god_mode": god_mode}

    if not get_enabled_tools():
        return {
            **state,
            "error": "No tools enabled — enable a tool under tools/*/manifest.yaml",
            "error_status": 503,
        }

    if not god_mode:
        for tool in get_enabled_tools():
            if backend_hint and tool.name != backend_hint:
                continue
            try:
                intent = tool.parse_rules(query, backend_hint)
            except Exception as exc:
                logger.debug("parse_rules failed for %s: %s", tool.name, exc)
                intent = None
            if intent:
                try:
                    tool.validate_intent(intent)
                except Exception as exc:
                    return {**state, **state_updates, "error": str(exc), "error_status": 422}
                await tracer.span(
                    request_id,
                    f"parse intent · rules · {tool.name}",
                    input={"query": query, "backend_hint": backend_hint, "god_mode": god_mode},
                    output=intent.model_dump(),
                    metadata={"step": "parse_intent", "parse_source": "rules"},
                )
                return {**state, **state_updates, "intent": intent, "parse_source": "rules"}

    if not settings.LLM_INTENT_ENABLED:
        return {
            **state,
            "error": "Could not parse intent from rules and LLM intent parsing is disabled",
            "error_status": 422,
        }

    llm = get_llm_client()
    if not llm.available:
        return {
            **state,
            "error": "Could not parse intent from rules and LLM is not configured",
            "error_status": 422,
        }

    system = build_intent_prompt(query, backend_hint, god_mode=god_mode)
    try:
        llm_result = await llm.chat_with_usage(
            system=system,
            user=query,
            request_id=request_id,
            backend=backend_hint,
            generation_name="tool-agent-intent",
        )
    except Exception as exc:
        logger.exception("LLM intent parse failed")
        return {**state, "error": f"LLM intent parse failed: {exc}", "error_status": 502}

    ledger: UsageLedger = state.get("usage_ledger") or UsageLedger()
    ledger.add_llm(
        LlmUsageRecord(
            name="parse_intent",
            model=llm_result.model,
            prompt_tokens=llm_result.usage.get("prompt_tokens", 0),
            completion_tokens=llm_result.usage.get("completion_tokens", 0),
            total_tokens=llm_result.usage.get("total_tokens", 0),
            cost_usd=llm_result.cost_usd,
            latency_ms=llm_result.latency_ms,
        )
    )

    try:
        data = _parse_llm_json(llm_result.content)
        intent = _normalize_intent(data, backend_hint)
        tool = get_tool(intent.backend)
        if not tool:
            return {
                **state,
                "error": f"LLM selected unknown backend '{intent.backend}'",
                "error_status": 422,
                "intent": intent,
                "parse_source": "llm",
                "usage_ledger": ledger,
            }
        tool.validate_intent(intent)
    except Exception as exc:
        return {
            **state,
            "error": f"Invalid LLM intent JSON: {exc}",
            "error_status": 422,
            "usage_ledger": ledger,
        }

    span_metadata: dict[str, object] = {"step": "parse_intent", "parse_source": "llm"}
    if god_mode:
        span_metadata["god_mode"] = True
    if llm_result.gateway_trace_id:
        span_metadata["gateway_trace_id"] = llm_result.gateway_trace_id
    span_metadata.update(
        {
            "tokens": llm_result.usage.get("total_tokens", 0),
            "prompt_tokens": llm_result.usage.get("prompt_tokens", 0),
            "completion_tokens": llm_result.usage.get("completion_tokens", 0),
        }
    )
    if llm_result.cost_usd is not None:
        span_metadata["cost_usd"] = llm_result.cost_usd

    span_id = await tracer.span(
        request_id,
        f"parse intent · llm · {intent.backend}.{intent.operation}",
        input={"query": query, "backend_hint": backend_hint},
        output=intent.model_dump(),
        metadata=span_metadata,
    )
    if llm.routing == "direct":
        await tracer.generation(
            request_id,
            "tool-agent-intent",
            model=llm_result.model,
            input={"query": query, "backend_hint": backend_hint},
            output=llm_result.content,
            usage=llm_result.usage,
            cost_usd=llm_result.cost_usd,
            latency_ms=llm_result.latency_ms,
            parent_observation_id=span_id,
            metadata={"step": "parse_intent", "source_name": "litellm/direct"},
        )

    return {
        **state,
        **state_updates,
        "intent": intent,
        "parse_source": "llm",
        "usage_ledger": ledger,
        "gateway_trace_id": llm_result.gateway_trace_id,
    }
