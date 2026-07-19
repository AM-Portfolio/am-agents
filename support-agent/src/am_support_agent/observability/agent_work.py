"""Agent-work event contract (mirrors agent_common.telemetry for Docker builds)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    from agent_common.telemetry import (  # type: ignore
        ALLOWED_LABEL_KEYS,
        EVENT_NAMES,
        AgentWorkEvent as _SharedEvent,
        WorkOutcome,
        WorkStatus,
        build_event as _shared_build,
        map_domain_status,
        sanitize_attributes,
    )

    HAS_AGENT_COMMON = True
except ImportError:  # pragma: no cover - docker image without libs/
    HAS_AGENT_COMMON = False

    class WorkStatus(str, Enum):
        PENDING = "pending"
        ACCEPTED = "accepted"
        RUNNING = "running"
        NEEDS_HUMAN = "needs_human"
        PASSED = "passed"
        PARTIAL = "partial"
        FAILED = "failed"
        CANCELLED = "cancelled"

    class WorkOutcome(str, Enum):
        RECOVERED = "recovered"
        CLOSED = "closed"
        NOT_CONFIRMED = "not_confirmed"
        HUMAN_HANDOFF = "human_handoff"
        GATED = "gated"
        FAILED = "failed"
        PARTIAL = "partial"
        CONTINUED = "continued"
        UNKNOWN = "unknown"

    OUTCOME_MAP = {
        "recovered": (WorkStatus.PASSED, WorkOutcome.RECOVERED),
        "closed": (WorkStatus.PASSED, WorkOutcome.CLOSED),
        "not_confirmed": (WorkStatus.PASSED, WorkOutcome.NOT_CONFIRMED),
        "human_required": (WorkStatus.NEEDS_HUMAN, WorkOutcome.HUMAN_HANDOFF),
        "gated": (WorkStatus.CANCELLED, WorkOutcome.GATED),
        "failed": (WorkStatus.FAILED, WorkOutcome.FAILED),
        "partial": (WorkStatus.PARTIAL, WorkOutcome.PARTIAL),
    }

    EVENT_NAMES = frozenset(
        {
            "agent.work.accepted",
            "agent.work.started",
            "agent.work.completed",
            "agent.work.failed",
            "agent.work.cancelled",
            "agent.work.continued_as_new",
            "incident.validation.completed",
            "incident.refired",
            "incident.recovered",
            "incident.not_confirmed",
            "incident.ticket.created",
            "incident.ticket.create.failed",
            "incident.ticket.closed",
            "incident.ticket.close.failed",
            "incident.hitl.required",
            "incident.hitl.signal.received",
            "incident.hitl.approval.received",
            "incident.hitl.feedback.received",
            "incident.hitl.resolved_external",
        }
    )
    ALLOWED_LABEL_KEYS = frozenset(
        {
            "agent",
            "work_kind",
            "event_name",
            "phase",
            "status",
            "outcome",
            "environment",
            "approval_purpose",
            "ticket_operation",
            "result",
            "error_class",
        }
    )

    def map_domain_status(domain_status: str):
        return OUTCOME_MAP.get(
            (domain_status or "").strip().lower(),
            (WorkStatus.FAILED, WorkOutcome.UNKNOWN),
        )

    def sanitize_attributes(value: Any, *, depth: int = 0) -> Any:
        if depth > 4:
            return "[truncated]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value if len(value) <= 512 else value[:512] + "…"
        if isinstance(value, dict):
            out = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= 40:
                    break
                key = str(k)
                if any(
                    f in key.lower()
                    for f in ("password", "secret", "token", "authorization", "api_key")
                ):
                    out[key] = "***"
                else:
                    out[key] = sanitize_attributes(v, depth=depth + 1)
            return out
        if isinstance(value, (list, tuple)):
            return [sanitize_attributes(v, depth=depth + 1) for v in list(value)[:20]]
        return str(value)[:512]


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


def build_event(**kwargs: Any) -> AgentWorkEvent:
    if HAS_AGENT_COMMON:
        shared = _shared_build(**kwargs)
        return AgentWorkEvent(**shared.to_dict())

    event_name = kwargs["event_name"]
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unknown event_name: {event_name}")
    agent = kwargs.get("agent") or "support-agent"
    work_kind = kwargs.get("work_kind") or "alert_incident"
    status = kwargs.get("status") or WorkStatus.RUNNING
    outcome = kwargs.get("outcome") or WorkOutcome.UNKNOWN
    status_v = status.value if isinstance(status, WorkStatus) else str(status)
    outcome_v = outcome.value if isinstance(outcome, WorkOutcome) else str(outcome)
    phase = kwargs.get("phase") or ""
    workflow_id = kwargs.get("workflow_id") or ""
    run_ref = kwargs.get("run_ref") or ""
    sequence = int(kwargs.get("sequence") or 0)
    ticket_operation = kwargs.get("ticket_operation") or ""
    labels = {
        k: str(v)[:64]
        for k, v in (kwargs.get("labels") or {}).items()
        if k in ALLOWED_LABEL_KEYS
    }
    labels.setdefault("agent", agent)
    labels.setdefault("work_kind", work_kind)
    labels.setdefault("event_name", event_name)
    labels.setdefault("status", status_v)
    labels.setdefault("outcome", outcome_v)
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
        event_id=kwargs.get("event_id") or str(uuid.uuid4()),
        event_name=event_name,
        occurred_at=kwargs.get("occurred_at") or _now(),
        dedupe_key=key,
        agent=agent,
        work_kind=work_kind,
        status=status_v,
        outcome=outcome_v,
        phase=phase,
        environment=kwargs.get("environment") or "",
        workflow_type=kwargs.get("workflow_type") or "AlertIncidentWorkflow",
        workflow_id=workflow_id,
        workflow_run_id=kwargs.get("workflow_run_id") or "",
        run_ref=run_ref,
        tracking_id=kwargs.get("tracking_id") or "",
        episode_id=kwargs.get("episode_id") or "",
        ticket_ref=kwargs.get("ticket_ref") or "",
        sequence=sequence,
        duration_ms=kwargs.get("duration_ms"),
        terminal=bool(kwargs.get("terminal") or False),
        labels=labels,
        attributes=sanitize_attributes(kwargs.get("attributes") or {}),
        error_class=kwargs.get("error_class") or "",
        error_code=kwargs.get("error_code") or "",
        error_message=(kwargs.get("error_message") or "")[:256],
        continued_from=kwargs.get("continued_from") or "",
    )


__all__ = [
    "ALLOWED_LABEL_KEYS",
    "EVENT_NAMES",
    "AgentWorkEvent",
    "WorkOutcome",
    "WorkStatus",
    "build_event",
    "dedupe_key",
    "map_domain_status",
    "sanitize_attributes",
]
