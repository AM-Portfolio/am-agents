"""Hard policy for incident auto actions — allowlist + no-delete (code enforces, not LLM)."""

from __future__ import annotations

import os
import re

from am_platform_ports.schemas.incident import IncidentDecision, ProposedAction

# Safe k8s / lab tools only — no delete/destroy
AUTO_ACTION_ALLOWLIST = frozenset(
    {
        "lab.noop",
        "lab.mark_fixed",
        "lab.pod_status",
        "lab.pod_restart",
        "k8s.pod_status",
        "k8s.pod_describe",
        "k8s.rollout_restart",
    }
)

_DENY_RE = re.compile(
    r"(delete|destroy|uninstall|wipe|rm\b|remove.?namespace|scale.?to.?zero)",
    re.IGNORECASE,
)


def _min_confidence() -> float:
    try:
        return float(os.getenv("ALERT_DECISION_MIN_CONFIDENCE", "0.6"))
    except ValueError:
        return 0.6


def action_denied(tool_name: str) -> bool:
    if _DENY_RE.search(tool_name or ""):
        return True
    return tool_name not in AUTO_ACTION_ALLOWLIST


def filter_actions(actions: list[ProposedAction]) -> tuple[list[ProposedAction], list[str]]:
    """Return (allowed, rejected_reasons)."""
    allowed: list[ProposedAction] = []
    rejected: list[str] = []
    for a in actions:
        name = (a.tool_name or "").strip()
        if _DENY_RE.search(name):
            rejected.append(f"denied:{name}")
            continue
        if name not in AUTO_ACTION_ALLOWLIST:
            rejected.append(f"not_allowlisted:{name}")
            continue
        allowed.append(a)
    return allowed, rejected


def enforce_decision(raw: IncidentDecision) -> IncidentDecision:
    """
    Apply hard policy:
    - low confidence → needs_human
    - auto_infra with delete / empty / bad tools → needs_human
    - strip illegal actions
    """
    decision = raw.decision
    rationale = raw.rationale
    actions, rejected = filter_actions(list(raw.proposed_actions))

    if raw.confidence < _min_confidence() and decision != "ignore":
        decision = "needs_human"
        rationale = f"{rationale} [policy: low confidence {raw.confidence}]".strip()

    if decision == "auto_infra":
        if rejected and not actions:
            decision = "needs_human"
            rationale = f"{rationale} [policy: all actions rejected: {', '.join(rejected)}]".strip()
        elif rejected:
            rationale = f"{rationale} [policy: dropped {', '.join(rejected)}]".strip()
        if not actions:
            # default safe probe if LLM forgot tools but chose auto_infra
            actions = [ProposedAction(tool_name="lab.pod_status", args={})]
        handoff = raw.handoff_agent or "kagent_infra"
    else:
        handoff = None if decision == "ignore" else raw.handoff_agent
        if decision != "auto_infra":
            actions = []

    return IncidentDecision(
        decision=decision,  # type: ignore[arg-type]
        confidence=raw.confidence,
        rationale=rationale,
        handoff_agent=handoff,
        proposed_actions=actions,
        ticket_update=raw.ticket_update or rationale,
        resolution_note=raw.resolution_note,
    )
