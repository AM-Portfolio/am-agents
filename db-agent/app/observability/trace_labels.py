"""Human-readable Langfuse span names, descriptions, and structured I/O."""

from __future__ import annotations

from typing import Any

from app.intent_schema import IntentDocument, ToolCall, ToolResult

SOURCE_NATIVE_ADAPTER = "native-adapter"
SOURCE_MCP_GATEWAY = "mcp-gateway"


def source_label(tool_call: ToolCall) -> str:
    if tool_call.source == "mcp":
        server = tool_call.mcp_server or "toolbox"
        tool = tool_call.mcp_tool or tool_call.operation
        return f"{SOURCE_MCP_GATEWAY}/{server}/{tool}"
    return f"{SOURCE_NATIVE_ADAPTER}/{tool_call.backend}"


def tool_fqn(backend: str, operation: str) -> str:
    return f"{backend}.{operation}"


def trace_name(
    backend: str | None,
    operation: str | None,
    *,
    pending: bool = False,
) -> str:
    """Top-level Langfuse trace name — visible in the traces list."""
    if backend and operation:
        return f"db-agent · {backend} · {operation}"
    if backend:
        suffix = " · …" if pending else ""
        return f"db-agent · {backend}{suffix}"
    return "db-agent · query"


def trace_tags(
    backend: str | None,
    operation: str | None,
    *,
    parse_source: str | None = None,
    agent_caller: str | None = None,
) -> list[str]:
    """Langfuse trace tags for sidebar filtering (backend, operation, etc.)."""
    tags = ["db-agent"]
    if backend:
        tags.append(f"backend:{backend}")
    if operation:
        tags.append(f"op:{operation}")
    if parse_source:
        tags.append(f"parse:{parse_source}")
    if agent_caller:
        tags.append(f"caller:{agent_caller}")
    return tags


def trace_metadata(
    *,
    backend: str | None = None,
    operation: str | None = None,
    backend_hint: str | None = None,
    parse_source: str | None = None,
    agent_caller: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured metadata for Langfuse trace filters (metadata.backend, etc.)."""
    meta: dict[str, Any] = {"source": "db-agent"}
    if backend:
        meta["backend"] = backend
    if operation:
        meta["operation"] = operation
    if backend_hint:
        meta["backend_hint"] = backend_hint
    if parse_source:
        meta["parse_source"] = parse_source
    if agent_caller:
        meta["agent_caller"] = agent_caller
    if extra:
        meta.update(extra)
    return meta


def parse_intent_span_name(*, parse_source: str, backend: str, operation: str) -> str:
    via = "LLM" if parse_source == "llm" else "rules"
    return f"parse intent · {via} → {tool_fqn(backend, operation)}"


def parse_intent_input(*, query: str, backend_hint: str | None) -> dict[str, Any]:
    return {
        "description": (
            "Turn the natural-language question into a structured intent: "
            "target backend, operation, and parameters."
        ),
        "example": (
            'e.g. "how many points in ui_patterns?" → '
            "qdrant.collection_info params={collection: ui_patterns}"
        ),
        "query": query,
        "backend_hint": backend_hint,
    }


def parse_intent_output(
    *,
    intent: IntentDocument,
    parse_source: str,
) -> dict[str, Any]:
    return {
        "status": "resolved",
        "message": (
            f"Intent resolved via {parse_source}: "
            f"{tool_fqn(intent.backend, intent.operation)} "
            f"(confidence={intent.confidence:.2f}, read_only={intent.read_only})"
        ),
        "backend": intent.backend,
        "operation": intent.operation,
        "params": intent.params,
        "parse_source": parse_source,
        "confidence": intent.confidence,
        "read_only": intent.read_only,
        "rationale": intent.rationale,
    }


def validate_safety_span_name(intent: IntentDocument) -> str:
    return f"validate safety · {tool_fqn(intent.backend, intent.operation)}"


def validate_safety_input(intent: IntentDocument, *, request_read_only: bool) -> dict[str, Any]:
    return {
        "description": (
            "Layer-2 safety gate: whitelist operation, block SQL writes, "
            "Redis destructive commands, Mongo writes, Qdrant/Kafka mutations."
        ),
        "example": (
            "e.g. blocks DELETE FROM users, COPY ..., Redis FLUSHALL, Mongo $out pipeline"
        ),
        "checking": {
            "backend": intent.backend,
            "operation": intent.operation,
            "params": intent.params,
            "intent_read_only": intent.read_only,
            "request_read_only": request_read_only,
        },
    }


def validate_safety_output_passed(intent: IntentDocument) -> dict[str, Any]:
    return {
        "status": "passed",
        "message": f"Safe to execute {tool_fqn(intent.backend, intent.operation)} in read-only mode",
        "checks": [
            "operation whitelisted in registry",
            "no destructive SQL/Redis/Mongo patterns in params",
            "read_only intent matches request",
        ],
    }


def validate_safety_output_blocked(reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "message": reason,
    }


def execute_tool_span_name(tool_call: ToolCall, *, fallback: bool = False) -> str:
    suffix = " (adapter fallback)" if fallback else ""
    return f"execute tool · {tool_fqn(tool_call.backend, tool_call.operation)} via {source_label(tool_call)}{suffix}"


def execute_tool_input(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "description": (
            "Layer-4 pre-flight + run the resolved tool against the infra database "
            "(native Python adapter or MCP gateway)."
        ),
        "example": (
            "e.g. qdrant.collection_info with params={collection: ui_patterns} "
            "via native-adapter/qdrant"
        ),
        "tool": {
            "backend": tool_call.backend,
            "operation": tool_call.operation,
            "method": tool_call.adapter_method or tool_call.mcp_tool or tool_call.operation,
            "source": tool_call.source,
            "source_name": source_label(tool_call),
            "mcp_server": tool_call.mcp_server,
            "read_only": tool_call.read_only,
            "params": tool_call.params,
        },
    }


def execute_tool_output_ok(
    tool_call: ToolCall,
    result: ToolResult,
    *,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "message": (
            f"{tool_fqn(tool_call.backend, tool_call.operation)} completed via "
            f"{source_label(tool_call)} in {duration_ms}ms"
        ),
        "source_name": source_label(tool_call),
        "tool_name": result.tool_name,
        "result_preview": result.data,
        "warnings": result.warnings,
        "latency_ms": duration_ms,
        "tokens": 0,
        "cost_usd": 0.0,
    }


def execute_tool_output_error(message: str) -> dict[str, Any]:
    return {"status": "error", "message": message}


def format_response_span_name(*, with_llm_summary: bool) -> str:
    if with_llm_summary:
        return "format response · LLM summary + JSON payload"
    return "format response · rule-based summary"


def format_response_input(*, include_summary: bool, backend: str, operation: str) -> dict[str, Any]:
    return {
        "description": (
            "Build the API response: truncate rows, optional LLM narrative summary, "
            "attach warnings and timing."
        ),
        "example": (
            'e.g. "10 points in ui_patterns, status green" from qdrant.collection_info result'
        ),
        "include_summary": include_summary,
        "resolved_tool": tool_fqn(backend, operation),
    }


def format_response_output(
    *,
    summary: str | None,
    warning_count: int,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "message": (
            f"Response ready ({duration_ms}ms, "
            f"summary={'LLM' if summary else 'rule-based'}, "
            f"warnings={warning_count})"
        ),
        "summary_preview": summary,
        "warning_count": warning_count,
        "duration_ms": duration_ms,
    }


def generation_intent_name() -> str:
    return "LLM · intent parser"


def generation_summary_name() -> str:
    return "LLM · result summary"
