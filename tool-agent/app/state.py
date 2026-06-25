from __future__ import annotations

from typing import Any, TypedDict

from app.models.intent import (
    IntentDocument,
    ParseSource,
    ToolCall,
    ToolResult,
    ToolsQueryRequest,
    ToolsQueryResponse,
    ToolsWriteConfirmation,
)
from app.observability.usage import UsageLedger


class ToolAgentState(TypedDict, total=False):
    request: ToolsQueryRequest
    request_id: str
    intent: IntentDocument
    tool_call: ToolCall
    tool_result: ToolResult
    response: ToolsQueryResponse
    error: str
    error_status: int
    max_rows: int
    started_ms: int
    usage_ledger: UsageLedger
    parse_source: ParseSource
    agent_caller: str | None
    gateway_trace_id: str | None
    resolved_params: dict[str, Any]
    entity: str | None
    write_confirmation: ToolsWriteConfirmation | None
