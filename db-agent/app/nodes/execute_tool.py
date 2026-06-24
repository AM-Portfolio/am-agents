from __future__ import annotations

import asyncio
import logging
import time

from adapters import run_adapter
from app.config import settings
from app.intent_schema import SafetyError, ToolResult
from app.observability.tracer import tracer
from app.observability.trace_labels import (
    execute_tool_input,
    execute_tool_output_error,
    execute_tool_output_ok,
    execute_tool_span_name,
    source_label,
)
from app.observability.usage import ToolUsageRecord, UsageLedger
from app.registry import get_registry
from app.safety import validate_tool_call
from app.state import DbAgentState
from mcp.pool import get_mcp_pool

logger = logging.getLogger(__name__)


async def resolve_and_execute_node(state: DbAgentState) -> DbAgentState:
    if state.get("error"):
        return state

    intent = state["intent"]
    request_id = state["request_id"]
    max_rows = state.get("max_rows") or state["request"].max_rows
    ledger = state.get("usage_ledger") or UsageLedger()
    registry = get_registry()
    tool_started = time.perf_counter()

    try:
        tool_call = registry.resolve(intent)
    except ValueError as exc:
        return {**state, "error": str(exc), "error_status": 400}

    try:
        validate_tool_call(tool_call)
    except SafetyError as exc:
        await tracer.span(
            request_id,
            execute_tool_span_name(tool_call),
            input=execute_tool_input(tool_call),
            output=execute_tool_output_error(exc.message),
            metadata={"step": "execute_tool", "source_name": source_label(tool_call)},
            level="WARNING",
        )
        return {**state, "error": exc.message, "error_status": 403}

    timeout = settings.DB_AGENT_TIMEOUT_SECONDS

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
        else:
            data = await asyncio.wait_for(
                run_adapter(
                    tool_call.backend,
                    tool_call.adapter_method or tool_call.operation,
                    tool_call.params,
                    read_only=tool_call.read_only,
                    max_rows=max_rows,
                ),
                timeout=timeout,
            )
            result = ToolResult(
                ok=True,
                data=data,
                tool_source="adapter",
                tool_name=tool_call.adapter_method or tool_call.operation,
            )
    except asyncio.TimeoutError:
        await tracer.span(
            request_id,
            execute_tool_span_name(tool_call),
            input=execute_tool_input(tool_call),
            output=execute_tool_output_error("Backend call timed out"),
            metadata={"step": "execute_tool", "source_name": source_label(tool_call)},
            level="ERROR",
        )
        return {**state, "error": "Backend call timed out", "error_status": 504}
    except Exception as exc:
        logger.exception("Tool execution failed")
        if tool_call.source == "mcp" and settings.MCP_ENABLED:
            try:
                data = await asyncio.wait_for(
                    run_adapter(
                        tool_call.backend,
                        tool_call.adapter_method or tool_call.operation,
                        tool_call.params,
                        read_only=tool_call.read_only,
                        max_rows=max_rows,
                    ),
                    timeout=timeout,
                )
                result = ToolResult(
                    ok=True,
                    data=data,
                    tool_source="adapter",
                    tool_name=tool_call.adapter_method or tool_call.operation,
                    warnings=[f"MCP failed ({exc}); used adapter fallback"],
                )
            except Exception as fallback_exc:
                await tracer.span(
                    request_id,
                    execute_tool_span_name(tool_call, fallback=True),
                    input=execute_tool_input(tool_call),
                    output=execute_tool_output_error(str(fallback_exc)),
                    metadata={"step": "execute_tool", "source_name": source_label(tool_call)},
                    level="ERROR",
                )
                return {
                    **state,
                    "error": f"MCP and adapter failed: {fallback_exc}",
                    "error_status": 502,
                }
        else:
            await tracer.span(
                request_id,
                execute_tool_span_name(tool_call),
                input=execute_tool_input(tool_call),
                output=execute_tool_output_error(str(exc)),
                metadata={"step": "execute_tool", "source_name": source_label(tool_call)},
                level="ERROR",
            )
            return {**state, "error": str(exc), "error_status": 502}

    tool_duration_ms = int((time.perf_counter() - tool_started) * 1000)
    ledger.add_tool(
        ToolUsageRecord(
            name=f"{tool_call.backend}.{tool_call.operation}",
            tool_source=source_label(tool_call),
            duration_ms=tool_duration_ms,
        )
    )

    await tracer.span(
        request_id,
        execute_tool_span_name(tool_call),
        input=execute_tool_input(tool_call),
        output=execute_tool_output_ok(tool_call, result, duration_ms=tool_duration_ms),
        metadata={
            "step": "execute_tool",
            "source_name": source_label(tool_call),
            "duration_ms": tool_duration_ms,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        },
    )

    return {**state, "tool_call": tool_call, "tool_result": result, "usage_ledger": ledger}
