"""HITL signal names and approval state for AlertIncident workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SIGNAL_APPROVE = "approve"  # legacy alias → investigation
SIGNAL_APPROVE_INVESTIGATION = "approve.investigation"
SIGNAL_APPROVE_KNOWN_FIX = "approve.known_fix"
SIGNAL_APPROVE_SILENCE = "approve.silence"
SIGNAL_ALERT_RESOLVED = "alert.resolved"
SIGNAL_ALERT_REFIRED = "alert.refired"
SIGNAL_FEEDBACK = "alert.feedback"

HITL_SIGNAL_NAMES: frozenset[str] = frozenset(
    {
        SIGNAL_APPROVE,
        SIGNAL_APPROVE_INVESTIGATION,
        SIGNAL_APPROVE_KNOWN_FIX,
        SIGNAL_APPROVE_SILENCE,
        SIGNAL_ALERT_RESOLVED,
        SIGNAL_ALERT_REFIRED,
        SIGNAL_FEEDBACK,
    }
)

APPROVAL_PURPOSES: frozenset[str] = frozenset(
    {"investigation", "known_fix", "silence"}
)


@dataclass
class ApprovalRecord:
    purpose: str
    request_id: str = ""
    actor: str = ""
    timestamp: str = ""
    scope_hash: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "request_id": self.request_id,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "scope_hash": self.scope_hash,
            "notes": self.notes,
        }


@dataclass
class HitlState:
    """Mutable HITL flags shared by AlertIncident-style workflows."""

    approved: bool = False  # legacy / investigation
    investigation_approved: bool = False
    known_fix_approved: bool = False
    silence_approved: bool = False
    resolved: bool = False
    refired: bool = False
    closed: bool = False
    notes: list[str] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    pending_feedback: dict[str, Any] | None = None
    last_approval: ApprovalRecord | None = None

    def apply_signal(self, name: str, payload: dict[str, Any] | None = None) -> None:
        body = dict(payload or {})
        if name in {SIGNAL_APPROVE, SIGNAL_APPROVE_INVESTIGATION}:
            self.approved = True
            self.investigation_approved = True
            rec = ApprovalRecord(
                purpose="investigation",
                request_id=str(body.get("request_id") or ""),
                actor=str(body.get("actor") or ""),
                timestamp=str(body.get("timestamp") or ""),
                scope_hash=str(body.get("scope_hash") or ""),
                notes=str(body.get("notes") or ""),
            )
            self.approvals.append(rec)
            self.last_approval = rec
            self.notes.append(name)
        elif name == SIGNAL_APPROVE_KNOWN_FIX:
            self.known_fix_approved = True
            rec = ApprovalRecord(
                purpose="known_fix",
                request_id=str(body.get("request_id") or ""),
                actor=str(body.get("actor") or ""),
                timestamp=str(body.get("timestamp") or ""),
                scope_hash=str(body.get("scope_hash") or ""),
                notes=str(body.get("notes") or ""),
            )
            self.approvals.append(rec)
            self.last_approval = rec
            self.notes.append(name)
        elif name == SIGNAL_APPROVE_SILENCE:
            self.silence_approved = True
            rec = ApprovalRecord(
                purpose="silence",
                request_id=str(body.get("request_id") or ""),
                actor=str(body.get("actor") or ""),
                timestamp=str(body.get("timestamp") or ""),
                scope_hash=str(body.get("scope_hash") or ""),
                notes=str(body.get("notes") or ""),
            )
            self.approvals.append(rec)
            self.last_approval = rec
            self.notes.append(name)
        elif name == SIGNAL_ALERT_RESOLVED:
            self.resolved = True
            self.notes.append(SIGNAL_ALERT_RESOLVED)
        elif name == SIGNAL_ALERT_REFIRED:
            self.refired = True
            self.resolved = False
            self.notes.append(SIGNAL_ALERT_REFIRED)
        elif name == SIGNAL_FEEDBACK:
            self.pending_feedback = body
            self.notes.append(SIGNAL_FEEDBACK)
        else:
            raise ValueError(f"unknown HITL signal: {name}")

    def waiting_satisfied(self) -> bool:
        return self.investigation_approved or self.approved or self.resolved or self.closed

    def known_fix_waiting_satisfied(self) -> bool:
        return self.known_fix_approved or self.closed

    def silence_waiting_satisfied(self) -> bool:
        return self.silence_approved or self.closed

    def consume_refired(self) -> bool:
        if self.refired:
            self.refired = False
            return True
        return False

    def consume_resolved(self) -> bool:
        if self.resolved:
            self.resolved = False
            return True
        return False

    def consume_feedback(self) -> dict[str, Any] | None:
        fb = self.pending_feedback
        self.pending_feedback = None
        return fb

    def as_dict(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "investigation_approved": self.investigation_approved,
            "known_fix_approved": self.known_fix_approved,
            "silence_approved": self.silence_approved,
            "resolved": self.resolved,
            "refired": self.refired,
            "closed": self.closed,
            "notes": list(self.notes),
            "approvals": [a.as_dict() for a in self.approvals],
            "pending_feedback": dict(self.pending_feedback or {}) or None,
        }


__all__ = [
    "SIGNAL_APPROVE",
    "SIGNAL_APPROVE_INVESTIGATION",
    "SIGNAL_APPROVE_KNOWN_FIX",
    "SIGNAL_APPROVE_SILENCE",
    "SIGNAL_ALERT_RESOLVED",
    "SIGNAL_ALERT_REFIRED",
    "SIGNAL_FEEDBACK",
    "HITL_SIGNAL_NAMES",
    "APPROVAL_PURPOSES",
    "ApprovalRecord",
    "HitlState",
]
