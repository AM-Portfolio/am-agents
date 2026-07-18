"""HITL signal names — must match legacy platform_worker for operator continuity.

Legacy source: `platform_worker/.../workflows/alert_incident.py`
Signals are identical strings so Temporal UI / gateway clients stay compatible
when traffic moves to queue `support-agent-v2`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Exact Temporal signal names (do not rename until Gate D cutover playbook).
SIGNAL_APPROVE = "approve"
SIGNAL_ALERT_RESOLVED = "alert.resolved"
SIGNAL_ALERT_REFIRED = "alert.refired"

HITL_SIGNAL_NAMES: frozenset[str] = frozenset(
    {SIGNAL_APPROVE, SIGNAL_ALERT_RESOLVED, SIGNAL_ALERT_REFIRED}
)


@dataclass
class HitlState:
    """Mutable HITL flags shared by AlertIncident-style workflows."""

    approved: bool = False
    resolved: bool = False
    refired: bool = False
    closed: bool = False
    notes: list[str] = field(default_factory=list)

    def apply_signal(self, name: str) -> None:
        if name == SIGNAL_APPROVE:
            self.approved = True
            self.notes.append(SIGNAL_APPROVE)
        elif name == SIGNAL_ALERT_RESOLVED:
            self.resolved = True
            self.notes.append(SIGNAL_ALERT_RESOLVED)
        elif name == SIGNAL_ALERT_REFIRED:
            self.refired = True
            self.notes.append(SIGNAL_ALERT_REFIRED)
        else:
            raise ValueError(f"unknown HITL signal: {name}")

    def waiting_satisfied(self) -> bool:
        return self.approved or self.resolved or self.closed

    def as_dict(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "resolved": self.resolved,
            "refired": self.refired,
            "closed": self.closed,
            "notes": list(self.notes),
        }


__all__ = [
    "SIGNAL_APPROVE",
    "SIGNAL_ALERT_RESOLVED",
    "SIGNAL_ALERT_REFIRED",
    "HITL_SIGNAL_NAMES",
    "HitlState",
]
