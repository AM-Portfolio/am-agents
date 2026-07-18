"""Structured incident notification model — one source for Cliq + email + OP comments."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

IncidentStatus = Literal[
    "INVESTIGATING",
    "AUTO_INFRA",
    "NEEDS_HUMAN",
    "RESOLVED",
    "FAILED",
]


class DeveloperNotes(BaseModel):
    """LLM or template notes for developers (failure / needs_human)."""

    developer_summary: str = ""
    likely_owner: str = ""
    gaps: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    info_needed_to_close: str = ""
    move_to_development: bool = False
    move_to_development_why: str = ""
    source: str = "template"  # template | llm


class DeveloperLinks(BaseModel):
    """Mandatory link group (order fixed). Empty url → show unavailable."""

    temporal_url: str = ""
    temporal_label: str = "Temporal"
    grafana_trace_url: str = ""
    grafana_trace_label: str = "Grafana trace"
    ticket_url: str = ""
    ticket_label: str = "OpenProject"
    alert_url: str = ""
    alert_label: str = "Alert"
    evidence_url: str = ""
    runbook_url: str = ""


class IncidentMessage(BaseModel):
    """Full incident report; chat uses a compact subset, mail uses all fields."""

    tracking_id: str = ""
    alert_id: str = ""  # alertname or fingerprint short
    ticket_ref: str = ""
    ticket_number: str = ""  # human WP id / Jira key
    status: IncidentStatus = "INVESTIGATING"
    env: str = ""
    severity: str = ""
    problem: str = ""
    reason: str = ""
    success_summary: str = ""
    done_by: str = ""
    responsible: str = ""
    backup: str = ""
    owner_source: str = ""
    team: str = ""
    app: str = ""
    namespace: str = ""
    started_at: str = ""
    notified_at: str = ""
    ended_at: str = ""
    decision: str = ""
    run_ref: str = ""
    workflow_id: str = ""
    run_id: str = ""
    mail_teaser: str = ""  # "Full report emailed to …"
    developer_notes: DeveloperNotes | None = None
    links: DeveloperLinks = Field(default_factory=DeveloperLinks)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def status_color(self) -> str:
        return {
            "RESOLVED": "#0d9488",  # teal
            "INVESTIGATING": "#2563eb",  # blue
            "AUTO_INFRA": "#2563eb",
            "NEEDS_HUMAN": "#d97706",  # amber
            "FAILED": "#dc2626",  # red
        }.get(self.status, "#475569")
