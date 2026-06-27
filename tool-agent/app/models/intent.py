from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParseSource = Literal["llm", "rules", "structured"]

UNIVERSAL_BACKENDS = frozenset({"postgres", "mongodb", "redis"})


class IntentDocument(BaseModel):
    backend: str
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class ToolsQueryRequest(BaseModel):
    query: str
    backend: str | None = None
    environment: str | None = None
    read_only: bool = True
    include_summary: bool = True
    max_rows: int = Field(default=100, ge=1, le=1000)


class ToolsPlanRequest(BaseModel):
    query: str
    backend: str | None = None
    read_only: bool = True


class ToolsWriteConfirmation(BaseModel):
    confirmation_token: str
    confirmation_phrase: str


class ToolsExecuteRequest(BaseModel):
    intent: IntentDocument
    include_summary: bool = False
    max_rows: int = Field(default=100, ge=1, le=1000)
    write_confirmation: ToolsWriteConfirmation | None = None


class ToolsPlanResponse(BaseModel):
    request_id: str
    intent: IntentDocument
    would_execute: str
    confidence_ok: bool
    parse_source: ParseSource
    min_confidence: float
    requires_write_confirmation: bool = False
    confirmation_token: str | None = None
    confirmation_phrase: str | None = None


class ToolsQueryResponse(BaseModel):
    request_id: str
    backend: str
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
    backend: str
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
