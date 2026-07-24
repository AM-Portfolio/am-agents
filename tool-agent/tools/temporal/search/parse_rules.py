from __future__ import annotations

from typing import Any

from app.models.intent import IntentDocument

KEYWORDS = ["temporal", "workflow", "run_id", "execution", "task_queue"]


def parse_rules(
    query: str, *, tool_name: str = "temporal", backend_hint: str | None = None
) -> IntentDocument | None:
    q_lower = query.lower()

    if backend_hint and backend_hint != tool_name:
        return None

    matched = any(kw in q_lower for kw in KEYWORDS)
    if not matched and not backend_hint:
        return None

    op = "list_workflows"
    params: dict[str, Any] = {}

    if "describe" in q_lower or "inspect" in q_lower or "get" in q_lower:
        op = "describe_workflow"
    elif "signal" in q_lower:
        op = "signal_workflow"
    elif "query" in q_lower:
        op = "query_workflow"
    elif "terminate" in q_lower or "cancel" in q_lower or "stop" in q_lower or "kill" in q_lower:
        op = "terminate_workflow"
    elif "list" in q_lower or "running" in q_lower or "completed" in q_lower or "failed" in q_lower:
        op = "list_workflows"
        if "running" in q_lower:
            params["status"] = "Running"
        elif "completed" in q_lower:
            params["status"] = "Completed"
        elif "failed" in q_lower:
            params["status"] = "Failed"

    return IntentDocument(
        backend=tool_name,
        tool_name=tool_name,
        operation=op,
        params=params,
        confidence=0.9 if matched else 0.7,
        raw_query=query,
    )
