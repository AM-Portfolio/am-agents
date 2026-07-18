"""Render IncidentMessage for Cliq (obs-platform style) and OpenProject (mid-detail)."""

from __future__ import annotations

from am_platform_ports.agent_identity import agent_display_name
from am_platform_ports.schemas.core import NotifyCard
from am_platform_ports.schemas.incident_message import DeveloperLinks, IncidentMessage

_STATUS_EMOJI = {
    "RESOLVED": "✅",
    "FAILED": "❌",
    "NEEDS_HUMAN": "🟠",
    "INVESTIGATING": "🔵",
    "AUTO_INFRA": "🔵",
}

_SEVERITY_UI = {
    "critical": {"emoji": "🔴", "label": "CRITICAL"},
    "error": {"emoji": "🔴", "label": "ERROR"},
    "high": {"emoji": "🟠", "label": "HIGH"},
    "warning": {"emoji": "🟡", "label": "WARNING"},
    "info": {"emoji": "🔵", "label": "INFO"},
    "unknown": {"emoji": "⚪", "label": "UNKNOWN"},
}


def _join(*parts: str, sep: str = " · ") -> str:
    return sep.join(p for p in parts if p and str(p).strip())


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


def to_cliq_card(msg: IncidentMessage, *, view_more_url: str | None = None) -> NotifyCard:
    """
    Compact Cliq card matching am-obs-platform alert format:
      text     — mention / thin placeholder (no duplicate title)
      card     — emoji · status · severity · alertname
      slides   — Field|Value table (summary, update, timing)
      buttons  — OpenProject / Alert / Temporal / Langfuse (Cliq ⋮ popup for overflow)

    Channel webhooks cannot open a custom in-chat form; link buttons stay inside Cliq
    (same pattern as original FIRING cards). Full HTML report stays in email.
    """
    _ = view_more_url  # kept for callers; Cliq no longer navigates to MinIO
    from am_platform_ports.formatting.cliq_details import incident_timing, langfuse_public_url

    aid = (msg.tracking_id or msg.alert_id or "AM").strip()
    status = (msg.status or "INVESTIGATING").strip().upper()
    alert_name = (msg.alert_id or msg.problem or "Incident").strip()
    # Prefer short alertname for title (not the full problem sentence)
    if ":" in alert_name and len(alert_name) > 40:
        alert_name = alert_name.split(":", 1)[0].strip() or alert_name
    alert_name = alert_name[:40]

    sev_raw = (msg.severity or "unknown").strip().lower()
    sev = _SEVERITY_UI.get(sev_raw, _SEVERITY_UI["unknown"])
    emoji = _STATUS_EMOJI.get(status, sev["emoji"])
    title = f"{emoji} {status} · {sev['label']} · {alert_name}"
    if len(title) > 80:
        title = title[:77] + "…"

    summary = (msg.problem or alert_name).strip()
    summary = " ".join(summary.split())
    if len(summary) > 120:
        summary = summary[:117] + "…"

    update = (msg.success_summary or msg.reason or "").strip()
    if not update:
        update = {
            "INVESTIGATING": "Investigation started",
            "AUTO_INFRA": "Automated infrastructure remediation in progress",
            "NEEDS_HUMAN": "Human review required",
            "RESOLVED": "Incident resolved and verification passed",
            "FAILED": "Incident handling or verification failed",
        }.get(status, "Incident updated")
    update = " ".join(update.split())
    update_teaser = update[:90] + ("…" if len(update) > 90 else "")

    where = _join(
        f"env={msg.env}" if msg.env else "",
        f"ns={msg.namespace}" if msg.namespace else "",
        f"app={msg.app}" if msg.app else "",
        f"team={msg.team}" if msg.team else "",
    )
    who = _join(
        msg.responsible or "",
        f"backup={msg.backup}" if msg.backup else "",
    )
    timing = incident_timing(msg)
    ids = _join(aid, f"ticket={msg.ticket_number}" if msg.ticket_number else "")

    table_rows: list[dict[str, str]] = []
    for field, value in (
        ("Summary", summary),
        ("Update", update_teaser),
        ("Where", where),
        ("Owners", who),
        ("Received", timing.get("received", "")),
        ("Resolution", timing.get("resolved", "")),
        ("Time spent", timing.get("time_spent", "")),
        ("IDs", ids),
        ("Done by", msg.done_by or agent_display_name()),
    ):
        if value:
            table_rows.append({"Field": field, "Value": value})

    links = msg.links
    # Same as original alert cards: short open.url buttons stay in Cliq (⋮ = popup)
    buttons: list[dict[str, str]] = []
    for label, url in (
        (links.ticket_label or "OpenProject", links.ticket_url),
        ("Open alert", links.alert_url),
        ("Temporal", links.temporal_url),
        ("Langfuse", langfuse_public_url()),
    ):
        if url and str(url).startswith("http") and len(str(url)) <= 256:
            buttons.append({"label": label[:30], "url": str(url), "action": "open.url"})
    buttons = buttons[:4]

    return NotifyCard(
        event=f"incident.{status.lower()}",
        title=title[:100],
        body=summary[:200],  # plain-fallback only; payload uses table
        refs={
            k: v
            for k, v in {
                "status": status,
                "env": msg.env,
                "ticket": msg.ticket_number or msg.ticket_ref,
                "alert_id": aid,
            }.items()
            if v
        },
        meta={
            "theme": "modern-inline",
            "mention": "\u200b",  # avoid duplicating title in chat (obs-platform style)
            "table_rows": table_rows,
            "buttons": buttons,
        },
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
