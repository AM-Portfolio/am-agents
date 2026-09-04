"""
shared/streaming/events.py — Canonical SSE streaming event schema.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any

@dataclass
class StreamEvent:
    type: str   # token | tool_start | tool_end | widget | done | error | cancelled
    content: str | None = None
    tool: str | None = None
    widget_id: str | None = None
    widget_params: dict | None = None
    trace_id: str | None = None
    session_id: str | None = None
    tools_used: list | None = None

    def to_sse(self) -> str:
        """Format as SSE line: data: {...}\n\n"""
        payload = {k: v for k, v in self.__dict__.items() if v is not None}
        return f"data: {json.dumps(payload)}\n\n"

    def to_json_line(self) -> str:
        payload = {k: v for k, v in self.__dict__.items() if v is not None}
        return json.dumps(payload)


# --- Helper constructors -------------------------------------------------------

def token_event(content: str, trace_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="token", content=content, trace_id=trace_id)

def tool_start_event(tool_name: str, trace_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="tool_start", tool=tool_name, trace_id=trace_id)

def tool_end_event(tool_name: str, trace_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="tool_end", tool=tool_name, trace_id=trace_id)

def widget_event(widget_id: str, widget_params: dict, trace_id: str | None = None, session_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="widget", widget_id=widget_id, widget_params=widget_params, trace_id=trace_id, session_id=session_id)

def done_event(tools_used: list, trace_id: str, session_id: str) -> StreamEvent:
    return StreamEvent(type="done", tools_used=tools_used, trace_id=trace_id, session_id=session_id)

def error_event(message: str, trace_id: str, session_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="error", content=message, trace_id=trace_id, session_id=session_id)

def cancelled_event(trace_id: str, session_id: str | None = None) -> StreamEvent:
    return StreamEvent(type="cancelled", trace_id=trace_id, session_id=session_id)
