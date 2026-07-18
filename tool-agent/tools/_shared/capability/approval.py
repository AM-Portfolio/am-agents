from __future__ import annotations

from typing import Any, Literal

ApprovalRisk = Literal["read", "create", "update", "send", "delete", "execute"]

_DEFAULT_RISK: dict[str, ApprovalRisk] = {
    "search": "read",
    "get": "read",
    "exists": "read",
    "status": "read",
    "create": "create",
    "comment": "update",
    "assign": "update",
    "transition": "update",
    "put": "create",
    "message.send": "send",
    "card.send": "send",
    "signed-url.create": "read",
    "owner.resolve": "read",
    "metrics.query": "read",
    "logs.query": "read",
    "timeseries.query": "read",
    "test-data.prepare": "create",
    "execute": "execute",
    "cancel": "update",
}


def risk_for_operation(operation: str, op_cfg: dict[str, Any] | None = None) -> ApprovalRisk:
    if op_cfg and op_cfg.get("approval_risk"):
        return str(op_cfg["approval_risk"])  # type: ignore[return-value]
    if operation in _DEFAULT_RISK:
        return _DEFAULT_RISK[operation]
    if op_cfg and op_cfg.get("read_only", True):
        return "read"
    return "update"


def requires_write_confirmation(risk: ApprovalRisk) -> bool:
    return risk in {"create", "update", "send", "delete", "execute"}
