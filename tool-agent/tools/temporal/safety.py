from __future__ import annotations

from typing import Any

from app.models.intent import IntentDocument

READ_ONLY_OPERATIONS = {"list_workflows", "describe_workflow", "query_workflow"}
MUTATING_OPERATIONS = {"signal_workflow", "terminate_workflow"}


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if request_read_only and intent.operation in MUTATING_OPERATIONS:
        raise ValueError(f"Operation '{intent.operation}' is mutating but read-only mode was requested")


def validate_tool_params(operation: str, params: dict[str, Any]) -> None:
    if operation in {"describe_workflow", "query_workflow", "signal_workflow", "terminate_workflow"}:
        if not params.get("workflow_id"):
            raise ValueError(f"operation '{operation}' requires parameter 'workflow_id'")
    if operation == "query_workflow" and not params.get("query_name"):
        raise ValueError("operation 'query_workflow' requires parameter 'query_name'")
    if operation == "signal_workflow" and not params.get("signal_name"):
        raise ValueError("operation 'signal_workflow' requires parameter 'signal_name'")
