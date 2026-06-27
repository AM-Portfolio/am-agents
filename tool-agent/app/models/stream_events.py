from __future__ import annotations

import json
from typing import Any, Literal

StreamEventType = Literal[
    "stage",
    "intent",
    "resolved",
    "safety",
    "executing",
    "result",
    "token",
    "done",
    "error",
]

StageName = Literal[
    "parse_intent",
    "resolve_params",
    "validate_safety",
    "check_intent_policy",
    "execute_tool",
    "format_response",
]


def sse_line(*, event: StreamEventType, data: dict[str, Any]) -> str:
    payload = {"event": event, **data}
    return f"data: {json.dumps(payload, default=str)}\n\n"


def stage_event(
    stage: StageName,
    status: Literal["started", "completed", "failed"],
    *,
    data: dict[str, Any] | None = None,
    ms: int | None = None,
) -> str:
    body: dict[str, Any] = {"stage": stage, "status": status}
    if data:
        body["data"] = data
    if ms is not None:
        body["ms"] = ms
    return sse_line(event="stage", data=body)
