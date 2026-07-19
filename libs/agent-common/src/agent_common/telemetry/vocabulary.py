"""Allowlisted statuses, outcomes, and event names for agent-work telemetry."""

from __future__ import annotations

from enum import Enum


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


# Domain terminal result → (status, outcome)
OUTCOME_MAP: dict[str, tuple[WorkStatus, WorkOutcome]] = {
    "recovered": (WorkStatus.PASSED, WorkOutcome.RECOVERED),
    "closed": (WorkStatus.PASSED, WorkOutcome.CLOSED),
    "not_confirmed": (WorkStatus.PASSED, WorkOutcome.NOT_CONFIRMED),
    "human_required": (WorkStatus.NEEDS_HUMAN, WorkOutcome.HUMAN_HANDOFF),
    "gated": (WorkStatus.CANCELLED, WorkOutcome.GATED),
    "failed": (WorkStatus.FAILED, WorkOutcome.FAILED),
    "partial": (WorkStatus.PARTIAL, WorkOutcome.PARTIAL),
}


def map_domain_status(domain_status: str) -> tuple[WorkStatus, WorkOutcome]:
    key = (domain_status or "").strip().lower()
    return OUTCOME_MAP.get(key, (WorkStatus.FAILED, WorkOutcome.UNKNOWN))


EVENT_NAMES: frozenset[str] = frozenset(
    {
        "agent.work.accepted",
        "agent.work.started",
        "agent.work.phase.started",
        "agent.work.phase.completed",
        "agent.work.phase.failed",
        "agent.work.status.changed",
        "agent.work.completed",
        "agent.work.failed",
        "agent.work.cancelled",
        "agent.work.continued_as_new",
        "incident.alert.normalized",
        "incident.memory.retrieved",
        "incident.evidence.observed",
        "incident.validation.completed",
        "incident.refired",
        "incident.resolution.reported",
        "incident.recovery.started",
        "incident.recovery.evaluated",
        "incident.recovered",
        "incident.not_confirmed",
        "incident.ticket.create.started",
        "incident.ticket.created",
        "incident.ticket.create.failed",
        "incident.ticket.assigned",
        "incident.ticket.assign.failed",
        "incident.ticket.commented",
        "incident.ticket.comment.failed",
        "incident.ticket.closed",
        "incident.ticket.close.failed",
        "incident.hitl.required",
        "incident.hitl.signal.received",
        "incident.hitl.approval.received",
        "incident.hitl.feedback.received",
        "incident.hitl.silence.requested",
        "incident.hitl.silence.applied",
        "incident.hitl.silence.failed",
        "incident.hitl.completed",
        "incident.hitl.resolved_external",
        "agent.activity.started",
        "agent.activity.completed",
        "agent.activity.failed",
        "agent.capability.completed",
        "agent.capability.failed",
    }
)

ALLOWED_LABEL_KEYS: frozenset[str] = frozenset(
    {
        "agent",
        "work_kind",
        "workflow_type",
        "event_name",
        "phase",
        "status",
        "outcome",
        "environment",
        "severity",
        "decision",
        "validation_status",
        "approval_purpose",
        "ticket_operation",
        "result",
        "error_class",
        "retryable",
        "recovery_status",
    }
)
