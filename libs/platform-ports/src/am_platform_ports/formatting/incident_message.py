"""Render IncidentMessage for Cliq (compact) and OpenProject (mid-detail)."""

from __future__ import annotations

from am_platform_ports.agent_identity import agent_display_name
from am_platform_ports.schemas.core import NotifyCard
from am_platform_ports.schemas.incident_message import DeveloperLinks, IncidentMessage


def _link_line(label: str, url: str, *, missing: str = "unavailable") -> str:
    if url:
        return f"{label}: {url}"
    return f"{label}: {missing}"


def developer_links_text(links: DeveloperLinks) -> str:
    lines = [
        _link_line("Temporal", links.temporal_url, missing="Temporal UI unavailable"),
        _link_line(
            "Grafana trace",
            links.grafana_trace_url,
            missing="Trace unavailable",
        ),
        _link_line(links.ticket_label, links.ticket_url, missing="Ticket URL unavailable"),
        _link_line("Alert", links.alert_url, missing="Alert link unavailable"),
    ]
    if links.evidence_url:
        lines.append(f"Evidence: {links.evidence_url}")
    if links.runbook_url:
        lines.append(f"Runbook: {links.runbook_url}")
    return "\n".join(lines)


def to_cliq_card(msg: IncidentMessage) -> NotifyCard:
    """Important-only chat card — short title, clean body; links via meta for Cliq list slide."""
    aid = msg.tracking_id or msg.alert_id or "AM"
    status = msg.status or "INVESTIGATING"
    problem = (msg.problem or "incident").strip()
    # Card title stays short so Cliq header does not truncate into garbage
    title = f"[{aid}] {status}"
    reason = (msg.success_summary or msg.reason or "").strip()
    body_parts = [
        problem[:180],
        f"Reason: {reason[:220]}" if reason else "",
    ]
    if msg.developer_notes and msg.status in {"FAILED", "NEEDS_HUMAN"}:
        teaser = (msg.developer_notes.developer_summary or "").strip()
        if teaser:
            body_parts.append(f"For developers: {teaser[:160]}")
        body_parts.append("Full developer notes in email.")
    if msg.mail_teaser:
        body_parts.append(msg.mail_teaser[:120])
    body = "\n".join(p for p in body_parts if p)

    refs: dict[str, str] = {
        "alert_id": aid,
        "ticket": msg.ticket_number or msg.ticket_ref,
        "status": status,
        "env": msg.env,
        "done_by": msg.done_by or agent_display_name(),
    }
    if msg.responsible:
        refs["responsible"] = msg.responsible

    links = msg.links
    buttons: list[dict[str, str]] = []
    for label, url in (
        ("Temporal", links.temporal_url),
        (links.ticket_label or "Ticket", links.ticket_url),
        ("Alert", links.alert_url),
        ("Grafana trace", links.grafana_trace_url),
    ):
        # Only real URLs become buttons — never "unavailable" noise in chat
        if url and str(url).startswith("http"):
            buttons.append({"label": label, "url": url})

    return NotifyCard(
        event=f"incident.{status.lower()}",
        title=title[:100],
        body=body[:900],
        refs={k: v for k, v in refs.items() if v},
        meta={"buttons": buttons[:4], "theme": "modern-inline"},
    )


def to_ticket_comment(
    msg: IncidentMessage,
    *,
    phase: str,
    extras: list[str] | None = None,
) -> str:
    """
    Phase-wise ticket comment for OpenProject *and* Jira.

    Each phase posts a full snapshot so if a later step fails, prior phases
    remain visible on the ticket. Plain text (Jira ADF wraps lines; OP markdown).
    """
    aid = msg.tracking_id or msg.alert_id or "AM"
    phase_u = (phase or msg.status or "UPDATE").strip().upper()
    provider = "Jira" if (msg.ticket_ref or "").startswith("jira:") else "OpenProject"
    lines = [
        f"=== [{aid}] Phase: {phase_u} · Status: {msg.status} ===",
        f"Provider: {provider}",
        f"Problem: {msg.problem or '—'}",
        f"Reason: {msg.success_summary or msg.reason or '—'}",
        f"Env: {msg.env or '—'} · Severity: {msg.severity or '—'}",
        f"Done by: {msg.done_by or agent_display_name()}",
    ]
    if msg.responsible:
        lines.append(f"Responsible: {msg.responsible}")
    if msg.backup:
        lines.append(f"Backup: {msg.backup}")
    if msg.team:
        lines.append(f"Team: {msg.team}")
    if msg.app or msg.namespace:
        lines.append(f"App/NS: {msg.app or '—'} / {msg.namespace or '—'}")
    if msg.decision:
        lines.append(f"Decision: {msg.decision}")
    if msg.run_ref:
        lines.append(f"Run: {msg.run_ref}")
    if msg.workflow_id:
        lines.append(f"Workflow: {msg.workflow_id}")
    if msg.started_at:
        lines.append(f"Started: {msg.started_at}")
    if msg.ended_at:
        lines.append(f"Ended: {msg.ended_at}")
    lines.append("")
    lines.append("--- Developer Links ---")
    lines.append(developer_links_text(msg.links))
    notes = msg.developer_notes
    if notes and (msg.status in {"FAILED", "NEEDS_HUMAN"} or phase_u in {"FAILED", "NEEDS_HUMAN", "ESCALATE"}):
        lines.append("")
        lines.append("--- For developers ---")
        if notes.developer_summary:
            lines.append(notes.developer_summary)
        for g in notes.gaps[:6]:
            lines.append(f"- gap: {g}")
        for s in notes.next_steps[:6]:
            lines.append(f"- next: {s}")
        if notes.info_needed_to_close:
            lines.append(f"- info needed: {notes.info_needed_to_close}")
        if notes.move_to_development:
            lines.append(f"- move to development: {notes.move_to_development_why or 'yes'}")
    if extras:
        lines.append("")
        lines.append("--- Phase details ---")
        lines.extend(extras)
    lines.append("")
    lines.append(
        f"(Phase checkpoint — earlier phases stay on this ticket if a later step fails.)"
    )
    return "\n".join(lines)


def to_op_comment(msg: IncidentMessage, *, phase: str | None = None) -> str:
    """Backward-compatible alias — prefer to_ticket_comment for phase-wise updates."""
    return to_ticket_comment(msg, phase=phase or msg.status)
