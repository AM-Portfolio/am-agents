"""Versioned AgentWorkEvent envelope."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent_common.telemetry.sanitize import sanitize_attributes
from agent_common.telemetry.vocabulary import (
    ALLOWED_LABEL_KEYS,
    EVENT_NAMES,
    WorkOutcome,
    WorkStatus,
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def dedupe_key(
    *,
    agent: str,
    event_name: str,
    workflow_id: str,
    run_ref: str,
    phase: str,
    sequence: int,
    ticket_operation: str = "",
) -> str:
    raw = "|".join(
        [
            agent,
            event_name,
            workflow_id or "",
            run_ref or "",
            phase or "",
            str(sequence),
            ticket_operation or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


@dataclass
class AgentWorkEvent:
    schema_version: str
    event_id: str
    event_name: str
    occurred_at: str
    dedupe_key: str
    agent: str
    work_kind: str
    status: str
    outcome: str
    phase: str = ""
    environment: str = ""
    workflow_type: str = ""
    workflow_id: str = ""
    workflow_run_id: str = ""
    run_ref: str = ""
    tracking_id: str = ""
    episode_id: str = ""
    ticket_ref: str = ""
    sequence: int = 0
    duration_ms: int | None = None
    terminal: bool = False
    labels: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    error_class: str = ""
    error_code: str = ""
    error_message: str = ""
    continued_from: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentWorkEvent:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def build_event(
    *,
    event_name: str,
    agent: str = "support-agent",
    work_kind: str = "alert_incident",
    status: WorkStatus | str = WorkStatus.RUNNING,
    outcome: WorkOutcome | str = WorkOutcome.UNKNOWN,
    phase: str = "",
    environment: str = "",
    workflow_type: str = "AlertIncidentWorkflow",
    workflow_id: str = "",
    workflow_run_id: str = "",
    run_ref: str = "",
    tracking_id: str = "",
    episode_id: str = "",
    ticket_ref: str = "",
    sequence: int = 0,
    duration_ms: int | None = None,
    terminal: bool = False,
    labels: dict[str, str] | None = None,
    attributes: dict[str, Any] | None = None,
    error_class: str = "",
    error_code: str = "",
    error_message: str = "",
    continued_from: str = "",
    occurred_at: str | None = None,
    event_id: str | None = None,
    ticket_operation: str = "",
) -> AgentWorkEvent:
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unknown event_name: {event_name}")
    status_v = status.value if isinstance(status, WorkStatus) else str(status)
    outcome_v = outcome.value if isinstance(outcome, WorkOutcome) else str(outcome)
    safe_labels = {
        k: str(v)[:64]
        for k, v in (labels or {}).items()
        if k in ALLOWED_LABEL_KEYS and v is not None and str(v)
    }
    safe_labels.setdefault("agent", agent)
    safe_labels.setdefault("work_kind", work_kind)
    safe_labels.setdefault("event_name", event_name)
    safe_labels.setdefault("status", status_v)
    safe_labels.setdefault("outcome", outcome_v)
    if phase:
        safe_labels.setdefault("phase", phase)
    if environment:
        safe_labels.setdefault("environment", environment)
    if ticket_operation:
        safe_labels.setdefault("ticket_operation", ticket_operation)
    key = dedupe_key(
        agent=agent,
        event_name=event_name,
        workflow_id=workflow_id,
        run_ref=run_ref,
        phase=phase,
        sequence=sequence,
        ticket_operation=ticket_operation,
    )
    return AgentWorkEvent(
        schema_version="1.0",
        event_id=event_id or str(uuid.uuid4()),
        event_name=event_name,
        occurred_at=occurred_at or _now(),
        dedupe_key=key,
        agent=agent,
        work_kind=work_kind,
        status=status_v,
        outcome=outcome_v,
        phase=phase,
        environment=environment,
        workflow_type=workflow_type,
        workflow_id=workflow_id,
        workflow_run_id=workflow_run_id,
        run_ref=run_ref,
        tracking_id=tracking_id,
        episode_id=episode_id,
        ticket_ref=ticket_ref,
        sequence=sequence,
        duration_ms=duration_ms,
        terminal=terminal,
        labels=safe_labels,
        attributes=sanitize_attributes(attributes or {}),
        error_class=error_class,
        error_code=error_code,
        error_message=(error_message or "")[:256],
        continued_from=continued_from,
    )
