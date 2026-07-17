"""RunStore schemas (ADR-005)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from am_platform_ports.schemas.enums import ErrorClass, RunKind, RunStatus, StepStatus


class AgentRun(BaseModel):
    run_ref: str
    kind: RunKind
    status: RunStatus = RunStatus.ACCEPTED
    parent_run_ref: str | None = None
    incident_ref: str | None = None
    ticket_ref: str | None = None
    demand_ref: str | None = None
    workflow_id: str | None = None
    requested_selector_hash: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentRunStep(BaseModel):
    step_ref: str
    run_ref: str
    name: str
    check_ref: str | None = None
    status: StepStatus = StepStatus.PENDING
    claim_lease_until: datetime | None = None
    worker_id: str | None = None
    attempts: int = 0
    last_error_class: ErrorClass | None = None
    result_ref: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateRunRequest(BaseModel):
    kind: RunKind
    status: RunStatus = RunStatus.ACCEPTED
    parent_run_ref: str | None = None
    incident_ref: str | None = None
    ticket_ref: str | None = None
    demand_ref: str | None = None
    workflow_id: str | None = None
    requested_selector_hash: str | None = None


class UpsertStepRequest(BaseModel):
    step_ref: str
    run_ref: str
    name: str
    status: StepStatus
    check_ref: str | None = None
    worker_id: str | None = None
    last_error_class: ErrorClass | None = None
    result_ref: str | None = None
    bump_attempts: bool = False
