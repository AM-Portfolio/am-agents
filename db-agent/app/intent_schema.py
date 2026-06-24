from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParseSource = Literal["llm", "rules", "structured"]

BackendName = Literal[
    "postgres", "mongodb", "redis", "kafka", "qdrant", "influx", "grafana", "loki"
]

BACKEND_OPERATIONS: dict[str, list[str]] = {
    "postgres": ["search_schema", "run_sql", "table_row_count"],
    "mongodb": [
        "list_databases",
        "list_collections",
        "find",
        "aggregate",
        "collection_schema",
        "count_documents",
    ],
    "redis": ["scan_keys", "get", "info", "type"],
    "kafka": ["list_topics", "describe_topic", "peek_messages", "consumer_lag"],
    "qdrant": ["list_collections", "collection_info", "scroll", "search"],
    "grafana": ["search_dashboards", "get_dashboard", "query_datasource"],
    "influx": ["query_flux", "query_influxql"],
    "loki": ["query_logs", "list_labels", "list_label_values", "query_patterns"],
}

UNIVERSAL_BACKENDS = frozenset({"postgres", "mongodb", "redis"})
SATELLITE_BACKENDS = frozenset({"kafka", "qdrant", "grafana", "influx", "loki"})


class IntentDocument(BaseModel):
    backend: BackendName
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class DbQueryRequest(BaseModel):
    query: str
    backend: BackendName | None = None
    environment: str | None = None
    read_only: bool = True
    include_summary: bool = True
    max_rows: int = Field(default=100, ge=1, le=1000)


class DbPlanRequest(BaseModel):
    query: str
    backend: BackendName | None = None
    read_only: bool = True


class DbExecuteRequest(BaseModel):
    intent: IntentDocument
    include_summary: bool = False
    max_rows: int = Field(default=100, ge=1, le=1000)


class DbPlanResponse(BaseModel):
    request_id: str
    intent: IntentDocument
    would_execute: str
    confidence_ok: bool
    parse_source: ParseSource
    min_confidence: float


class DbQueryResponse(BaseModel):
    request_id: str
    backend: BackendName
    operation: str
    read_only: bool
    confidence: float
    parse_source: ParseSource = "rules"
    tool_source: Literal["mcp", "adapter"]
    tool_name: str
    data: Any
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int
    gateway_trace_id: str | None = None
    resolved_params: dict[str, Any] = Field(default_factory=dict)
    entity: str | None = None


class ToolCall(BaseModel):
    backend: BackendName
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)
    source: Literal["mcp", "adapter"]
    mcp_server: str | None = None
    mcp_tool: str | None = None
    adapter_method: str | None = None
    read_only: bool = True


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None
    tool_source: Literal["mcp", "adapter"]
    tool_name: str
    warnings: list[str] = Field(default_factory=list)


class SafetyError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
