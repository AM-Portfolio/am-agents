from __future__ import annotations

from app.models.intent import IntentDocument, SafetyError
from tools._shared.mcp_satellite_adapter import READ_ONLY_OPERATIONS

WRITE_OPERATIONS = frozenset(
    {
        "update_dashboard",
        "create_incident",
        "alerting_manage_rules",
        "alerting_manage_routing",
    }
)


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if intent.operation in WRITE_OPERATIONS:
        raise SafetyError(f"Grafana write operation '{intent.operation}' is blocked")
    if intent.operation not in READ_ONLY_OPERATIONS:
        raise SafetyError(f"Unknown or disallowed grafana operation '{intent.operation}'")
    if request_read_only and not intent.read_only:
        raise SafetyError("Intent marked read_only=false but request requires read-only")


def validate_tool_params(operation: str, params: dict) -> None:
    if operation not in READ_ONLY_OPERATIONS:
        raise SafetyError(f"Grafana operation '{operation}' is not allowed")
    if operation == "query_logs" and not (params.get("query") or params.get("logql")):
        raise SafetyError("query_logs requires params.query (LogQL)")
