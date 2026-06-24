from __future__ import annotations

from typing import Any, TypedDict

from app.intent_schema import DbQueryRequest, DbQueryResponse, IntentDocument, ParseSource, ToolCall, ToolResult
from app.observability.usage import UsageLedger


class DbAgentState(TypedDict, total=False):
    request: DbQueryRequest
    request_id: str
    intent: IntentDocument
    tool_call: ToolCall
    tool_result: ToolResult
    response: DbQueryResponse
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
