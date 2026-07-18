from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from tools._shared.capability.errors import ErrorClass


class CapabilityResult(BaseModel):
    ok: bool = True
    capability: str = ""
    provider: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_class: ErrorClass | None = None
    approval_risk: str = "read"
    idempotency_key: str | None = None
    async_operation_ref: str | None = None
    status: Literal["completed", "accepted", "failed"] = "completed"


def normalize_result(
    *,
    capability: str,
    provider: str,
    data: dict[str, Any] | None = None,
    ok: bool = True,
    error: str | None = None,
    error_class: ErrorClass | None = None,
    approval_risk: str = "read",
    idempotency_key: str | None = None,
    async_operation_ref: str | None = None,
) -> dict[str, Any]:
    status: Literal["completed", "accepted", "failed"] = "completed"
    if not ok:
        status = "failed"
    elif async_operation_ref:
        status = "accepted"
    return CapabilityResult(
        ok=ok,
        capability=capability,
        provider=provider,
        data=data or {},
        error=error,
        error_class=error_class,
        approval_risk=approval_risk,
        idempotency_key=idempotency_key,
        async_operation_ref=async_operation_ref,
        status=status,
    ).model_dump()
