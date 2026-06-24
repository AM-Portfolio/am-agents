from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings
from app.models.intent import SafetyError, ToolResult, ToolsQueryResponse
from app.observability.tracer import tracer
from app.observability.usage import ToolUsageRecord, UsageLedger
from app.registry import get_registry
from app.safety import validate_tool_call
from app.state import ToolAgentState
from mcp.pool import get_mcp_pool
from tools._loader import get_tool

logger = logging.getLogger(__name__)


async def resolve_and_execute_node(state: ToolAgentState) -> ToolAgentState:
    if state.get("error"):
        return state

    intent = state["intent"]
    request_id = state["request_id"]
    max_rows = state.get("max_rows") or state["request"].max_rows
    ledger: UsageLedger = state.get("usage_ledger") or UsageLedger()
    registry = get_registry()
    tool_started = time.perf_counter()

    try:
        tool_call = registry.resolve(intent)
    except ValueError as exc:
        return {**state, "error": str(exc), "error_status": 400}

    try:
        validate_tool_call(tool_call)
    except SafetyError as exc:
        return {**state, "error": exc.message, "error_status": 403}

    timeout = settings.TOOL_AGENT_TIMEOUT_SECONDS
    integration = get_tool(intent.backend)

    try:
        if tool_call.source == "mcp" and settings.MCP_ENABLED:
            pool = get_mcp_pool()
            data = await asyncio.wait_for(
                pool.call_tool(
                    tool_call.mcp_server or "",
                    tool_call.mcp_tool or tool_call.operation,
                    tool_call.params,
                ),
                timeout=timeout,
            )
            result = ToolResult(
                ok=True,
                data=data,
                tool_source="mcp",
                tool_name=tool_call.mcp_tool or tool_call.operation,
            )
        elif integration:
            data = await asyncio.wait_for(
                integration.execute(intent, read_only=tool_call.read_only, max_rows=max_rows),
                timeout=timeout,
            )
            result = ToolResult(
                ok=True,
                data=data,
                tool_source="adapter",
                tool_name=tool_call.adapter_method or tool_call.operation,
            )
        else:
            return {**state, "error": f"No adapter for backend '{intent.backend}'", "error_status": 502}
    except asyncio.TimeoutError:
        return {**state, "error": f"Tool execution timed out after {timeout}s", "error_status": 504}
    except Exception as exc:
        logger.exception("tool execution failed")
        return {**state, "error": str(exc), "error_status": 502}

    duration_ms = int((time.perf_counter() - tool_started) * 1000)
    ledger.add_tool(
        ToolUsageRecord(
            name=f"{intent.backend}.{intent.operation}",
            tool_source=result.tool_source,
            duration_ms=duration_ms,
        )
    )

    parse_source = state.get("parse_source") or "rules"
    response = ToolsQueryResponse(
        request_id=request_id,
        backend=intent.backend,
        operation=intent.operation,
        read_only=intent.read_only,
        confidence=intent.confidence,
        parse_source=parse_source,
        tool_source=result.tool_source,
        tool_name=result.tool_name,
        data=result.data,
        warnings=result.warnings,
        duration_ms=duration_ms,
        gateway_trace_id=state.get("gateway_trace_id"),
        resolved_params=state.get("resolved_params") or intent.params,
        entity=state.get("entity"),
    )
    await tracer.span(
        request_id,
        f"execute · {intent.backend}.{intent.operation}",
        input={
            "backend": intent.backend,
            "operation": intent.operation,
            "params": state.get("resolved_params") or intent.params,
            "tool_source": tool_call.source,
        },
        output={
            "tool_source": result.tool_source,
            "tool_name": result.tool_name,
            "duration_ms": duration_ms,
            "ok": result.ok,
        },
        metadata={"step": "execute_tool"},
    )
    return {**state, "tool_call": tool_call, "tool_result": result, "response": response, "usage_ledger": ledger}
