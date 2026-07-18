"""Build + send dual-channel incident notifications (Cliq compact + HTML mail)."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from am_platform_adapters.links import build_developer_links, ticket_number
from am_platform_ports.agent_identity import agent_display_name
from am_platform_ports.formatting.incident_email import (
    email_subject,
    render_incident_email_html,
    render_incident_email_text,
)
from am_platform_ports.formatting.incident_message import to_cliq_card, to_ticket_comment
from am_platform_ports.schemas.incident_message import (
    DeveloperNotes,
    IncidentMessage,
    IncidentStatus,
)

LOG = logging.getLogger("platform_worker.notify")


def soft_ticket_comment(ports: Any, *, ticket_ref: str, body: str) -> str:
    """Never raise — prior phase comments must survive later failures."""
    if not ticket_ref or not (body or "").strip():
        return "skipped"
    try:
        ports.tickets.comment(ticket_ref=ticket_ref, body=body[:30000])
        return "ok"
    except Exception as exc:  # noqa: BLE001
        LOG.warning("ticket comment soft-fail ticket=%s: %s", ticket_ref, exc)
        return f"error:{exc}"[:160]


def comment_incident_phase(
    ports: Any,
    *,
    msg: IncidentMessage,
    phase: str,
    extras: list[str] | None = None,
) -> str:
    """Post a full phase snapshot to Jira/OpenProject (same formatter for both)."""
    if not msg.ticket_ref:
        return "skipped"
    cleaned = [e for e in (extras or []) if e and str(e).strip()]
    body = to_ticket_comment(msg, phase=phase, extras=cleaned or None)
    return soft_ticket_comment(ports, ticket_ref=msg.ticket_ref, body=body)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_incident_message(
    *,
    status: IncidentStatus,
    tracking_id: str = "",
    alert: dict[str, Any] | None = None,
    ticket_ref: str = "",
    ticket_url: str | None = None,
    env: str = "",
    reason: str = "",
    success_summary: str = "",
    decision: str = "",
    run_ref: str = "",
    workflow_id: str = "",
    run_id: str = "",
    done_by: str | None = None,
    responsible: str = "",
    backup: str = "",
    owner_source: str = "",
    assignee_email: str = "",
    backup_email: str = "",
    evidence_url: str = "",
    developer_notes: DeveloperNotes | None = None,
    ended: bool = False,
) -> IncidentMessage:
    alert = alert or {}
    labels = dict(alert.get("labels") or {})
    annotations = dict(alert.get("annotations") or {})
    problem = (
        str(alert.get("summary") or annotations.get("summary") or labels.get("alertname") or "Incident")
    ).strip()
    value = str(alert.get("value_string") or "").strip()
    if value and value not in problem:
        problem = f"{problem} ({value})" if problem else value

    alertname = str(labels.get("alertname") or alert.get("alertname") or "").strip()
    tid = (tracking_id or "").strip() or str(alert.get("fingerprint") or alertname or "AM")[:40]
    links = build_developer_links(
        ticket_ref=ticket_ref,
        ticket_url=ticket_url,
        generator_url=alert.get("generator_url"),
        trace_id=alert.get("trace_id") or labels.get("trace_id"),
        workflow_id=workflow_id,
        run_id=run_id,
        env=env,
        evidence_url=evidence_url,
        runbook_url=annotations.get("runbook") or annotations.get("runbook_url"),
    )
    from am_platform_ports.schemas.incident_message import DeveloperLinks

    mail_to = [e for e in (assignee_email, backup_email) if e]
    cc = [x.strip() for x in (os.getenv("INCIDENT_MAIL_CC") or "").split(",") if x.strip()]
    recipients = list(dict.fromkeys(mail_to + cc))
    teaser = (
        f"Full report emailed to {', '.join(recipients)}"
        if recipients and os.getenv("INCIDENT_MAIL_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
        else "Mail skipped: no recipient"
    )

    return IncidentMessage(
        tracking_id=tid,
        alert_id=alertname or tid,
        ticket_ref=ticket_ref,
        ticket_number=ticket_number(ticket_ref),
        status=status,
        env=env or str(labels.get("env") or ""),
        severity=str(labels.get("severity") or alert.get("priority") or "").upper(),
        problem=problem,
        reason=reason,
        success_summary=success_summary,
        done_by=done_by or agent_display_name(),
        responsible=responsible,
        backup=backup,
        owner_source=owner_source,
        team=str(labels.get("team") or ""),
        app=str(labels.get("application") or labels.get("app") or labels.get("service") or ""),
        namespace=str(labels.get("namespace") or ""),
        started_at=str(alert.get("starts_at") or "")[:64],
        notified_at=_now_iso(),
        ended_at=_now_iso() if ended else "",
        decision=decision,
        run_ref=run_ref,
        workflow_id=workflow_id,
        run_id=run_id,
        mail_teaser=teaser,
        developer_notes=developer_notes,
        links=DeveloperLinks.model_validate(links),
        extra={"mail_to": recipients},
    )


def post_cliq_card(
    ports: Any,
    *,
    msg: IncidentMessage,
    channel_ref: str,
) -> dict[str, str]:
    """Send Cliq card only. Returns status + ref for Temporal visibility."""
    channel = (channel_ref or "cliq:lab").strip() or "cliq:lab"
    try:
        ref = ports.notifier.send_card(channel_ref=channel, card=to_cliq_card(msg))
        return {
            "status": "ok",
            "cliq_ref": str(ref or ""),
            "channel_ref": channel,
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warning("cliq notify failed: %s", exc)
        return {
            "status": "error",
            "cliq_ref": "",
            "channel_ref": channel,
            "error": str(exc)[:300],
        }


def send_incident_mail_msg(ports: Any, *, msg: IncidentMessage) -> dict[str, str]:
    """Send HTML mail only. Soft-fails; returns status + ref for Temporal visibility."""
    mail_enabled = os.getenv("INCIDENT_MAIL_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    recipients = list(msg.extra.get("mail_to") or [])
    if not mail_enabled:
        return {"status": "skipped", "mail_ref": "disabled", "recipients": "", "error": ""}
    if not recipients:
        return {"status": "skipped", "mail_ref": "no_recipient", "recipients": "", "error": ""}
    if not getattr(ports, "mail", None):
        return {"status": "skipped", "mail_ref": "no_mail_port", "recipients": "", "error": ""}
    try:
        ref = ports.mail.send(
            to=recipients,
            subject=email_subject(msg),
            body=render_incident_email_text(msg),
            html_body=render_incident_email_html(msg),
            refs={
                "tracking_id": msg.tracking_id,
                "ticket_ref": msg.ticket_ref,
                "status": msg.status,
            },
        )
        return {
            "status": "ok",
            "mail_ref": str(ref or ""),
            "recipients": ",".join(recipients),
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warning("mail notify failed (soft): %s", exc)
        return {
            "status": "error",
            "mail_ref": "",
            "recipients": ",".join(recipients),
            "error": str(exc)[:300],
        }


def notify_incident_channels(
    ports: Any,
    *,
    msg: IncidentMessage,
    channel_ref: str,
    also_ticket_comment: bool = True,
) -> dict[str, str]:
    """Send compact Cliq + optional HTML mail; soft-fail each channel. Optionally comment OP."""
    cliq = post_cliq_card(ports, msg=msg, channel_ref=channel_ref)
    out: dict[str, str] = {
        "cliq": cliq.get("cliq_ref") or (f"error:{cliq['error']}" if cliq.get("error") else ""),
        "cliq_status": cliq.get("status") or "",
        "mail": "",
        "mail_status": "",
        "ticket_comment": "",
    }

    if also_ticket_comment and msg.ticket_ref:
        out["ticket_comment"] = comment_incident_phase(
            ports, msg=msg, phase=msg.status
        )

    mail = send_incident_mail_msg(ports, msg=msg)
    out["mail"] = mail.get("mail_ref") or (
        f"error:{mail['error']}" if mail.get("error") else mail.get("status") or ""
    )
    out["mail_status"] = mail.get("status") or ""
    return out
