"""Modern HTML email template for incident reports (email-safe tables)."""

from __future__ import annotations

import html
from am_platform_ports.agent_identity import agent_display_name
from am_platform_ports.formatting.cliq_details import incident_timing, langfuse_public_url
from am_platform_ports.schemas.incident_message import IncidentMessage


def _e(value: str | None) -> str:
    return html.escape((value or "").strip())


def _btn(label: str, url: str, *, color: str = "#0f766e") -> str:
    if not url:
        return (
            f'<td style="padding:6px 8px 6px 0;">'
            f'<span style="display:inline-block;padding:10px 14px;border-radius:8px;'
            f'background:#e2e8f0;color:#64748b;font-size:13px;font-weight:600;">'
            f"{_e(label)} · unavailable</span></td>"
        )
    return (
        f'<td style="padding:6px 8px 6px 0;">'
        f'<a href="{_e(url)}" style="display:inline-block;padding:10px 14px;border-radius:8px;'
        f"background:{color};color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;\">"
        f"{_e(label)}</a></td>"
    )


def _row(label: str, value: str) -> str:
    if not (value or "").strip():
        return ""
    return (
        f'<tr>'
        f'<td style="padding:8px 12px;width:34%;color:#64748b;font-size:13px;'
        f'border-bottom:1px solid #e2e8f0;">{_e(label)}</td>'
        f'<td style="padding:8px 12px;color:#0f172a;font-size:13px;font-weight:500;'
        f'border-bottom:1px solid #e2e8f0;">{_e(value)}</td>'
        f"</tr>"
    )


def render_incident_email_html(msg: IncidentMessage) -> str:
    color = msg.status_color
    aid = _e(msg.tracking_id or msg.alert_id or "AM")
    status = _e(msg.status)
    problem = _e(msg.problem or "Incident")
    reason = _e(msg.success_summary or msg.reason or "—")
    agent = _e(msg.done_by or agent_display_name())
    timing = incident_timing(msg)

    detail_rows = "".join(
        r
        for r in (
            _row("Alert ID", msg.tracking_id or msg.alert_id),
            _row("Ticket", msg.ticket_number or msg.ticket_ref),
            _row("Severity", msg.severity),
            _row("Status", msg.status),
            _row("Env", msg.env),
            _row("App", msg.app),
            _row("Namespace", msg.namespace),
            _row("Alert name", msg.alert_id),
            _row("Team", msg.team),
            _row("Started", msg.started_at),
            _row("Notified", msg.notified_at),
            _row("Ended", msg.ended_at),
            _row("Received date", timing.get("received", "")),
            _row("Resolution date", timing.get("resolved", "")),
            _row("Time spent", timing.get("time_spent", "")),
            _row("Responsible", msg.responsible),
            _row("Backup", msg.backup),
            _row("Done by", msg.done_by or agent_display_name()),
            _row("Owner source", msg.owner_source),
            _row("Decision", msg.decision),
            _row("Run", msg.run_ref),
        )
        if r
    )

    links = msg.links
    buttons = (
        "<tr>"
        + _btn("Temporal", links.temporal_url, color="#1e293b")
        + _btn("Grafana trace", links.grafana_trace_url, color="#0f766e")
        + _btn(links.ticket_label or "Ticket", links.ticket_url, color="#2563eb")
        + _btn("Alert", links.alert_url, color="#7c3aed")
        + _btn("Langfuse", langfuse_public_url(), color="#d97706")
        + "</tr>"
    )
    extra_btns = ""
    if links.evidence_url or links.runbook_url:
        extra_btns = (
            "<tr>"
            + (_btn("Evidence", links.evidence_url, color="#0d9488") if links.evidence_url else "")
            + (_btn("Runbook", links.runbook_url, color="#475569") if links.runbook_url else "")
            + "</tr>"
        )

    dev_block = ""
    notes = msg.developer_notes
    if notes and msg.status in {"FAILED", "NEEDS_HUMAN"}:
        gaps = "".join(f"<li style=\"margin:0 0 6px;\">{_e(g)}</li>" for g in notes.gaps[:6])
        steps = "".join(f"<li style=\"margin:0 0 6px;\">{_e(s)}</li>" for s in notes.next_steps[:6])
        move = ""
        if notes.move_to_development:
            move = (
                f'<p style="margin:12px 0 0;font-size:13px;color:#b91c1c;">'
                f"<strong>Move to development:</strong> {_e(notes.move_to_development_why or 'yes')}</p>"
            )
        info = ""
        if notes.info_needed_to_close:
            info = (
                f'<p style="margin:12px 0 0;font-size:13px;color:#0f172a;">'
                f"<strong>Info needed to close:</strong> {_e(notes.info_needed_to_close)}</p>"
            )
        owner = f" · likely owner: {_e(notes.likely_owner)}" if notes.likely_owner else ""
        dev_block = f"""
        <tr>
          <td style="padding:24px 28px 8px;">
            <div style="border:1px solid #fed7aa;border-radius:12px;background:#fffbeb;padding:18px 20px;">
              <div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#b45309;font-weight:700;">
                For developers{owner}
              </div>
              <p style="margin:10px 0 0;font-size:14px;color:#0f172a;line-height:1.5;">
                {_e(notes.developer_summary)}
              </p>
              {"<p style='margin:14px 0 4px;font-size:12px;color:#92400e;font-weight:700;'>Gaps</p><ul style='margin:0;padding-left:18px;color:#78350f;font-size:13px;'>" + gaps + "</ul>" if gaps else ""}
              {"<p style='margin:14px 0 4px;font-size:12px;color:#92400e;font-weight:700;'>Next steps</p><ul style='margin:0;padding-left:18px;color:#78350f;font-size:13px;'>" + steps + "</ul>" if steps else ""}
              {info}{move}
              <p style="margin:12px 0 0;font-size:11px;color:#a8a29e;">notes source: {_e(notes.source)}</p>
            </div>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>[{aid}] {status}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
        <tr>
          <td style="background:{color};padding:22px 28px;color:#ffffff;">
            <div style="font-size:12px;opacity:0.9;letter-spacing:0.08em;text-transform:uppercase;font-weight:600;">
              IT Support · {_e(msg.env or "unknown")}
            </div>
            <div style="margin-top:8px;font-size:22px;font-weight:700;line-height:1.25;">
              [{aid}] {status}
            </div>
            <div style="margin-top:8px;font-size:14px;opacity:0.95;line-height:1.4;">{problem}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 28px 8px;">
            <div style="display:inline-block;padding:6px 12px;border-radius:999px;background:{color}22;color:{color};font-size:12px;font-weight:700;">
              {status}
            </div>
            <p style="margin:14px 0 0;font-size:14px;color:#0f172a;line-height:1.5;">
              <strong>Reason:</strong> {reason}
            </p>
            <p style="margin:8px 0 0;font-size:13px;color:#475569;">Done by · {agent}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 8px;">
            <div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;font-weight:700;margin-bottom:8px;">Details</div>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
              {detail_rows}
            </table>
          </td>
        </tr>
        {dev_block}
        <tr>
          <td style="padding:16px 28px 8px;">
            <div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;font-weight:700;margin-bottom:10px;">Developer Links</div>
            <table role="presentation" cellspacing="0" cellpadding="0"><tbody>{buttons}{extra_btns}</tbody></table>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 28px 28px;color:#94a3b8;font-size:11px;line-height:1.5;">
            Sent by {_e(agent_display_name())}. Tracking {_e(msg.tracking_id or msg.alert_id)}.
            Do not reply to this automated message.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_incident_email_text(msg: IncidentMessage) -> str:
    lines = [
        f"[{msg.tracking_id or msg.alert_id}] {msg.status}",
        msg.problem or "",
        f"Reason: {msg.success_summary or msg.reason}",
        f"Env: {msg.env}",
        f"Ticket: {msg.ticket_number or msg.ticket_ref}",
        f"Done by: {msg.done_by or agent_display_name()}",
        "",
        "Developer Links:",
        f"  Temporal: {msg.links.temporal_url or 'unavailable'}",
        f"  Grafana trace: {msg.links.grafana_trace_url or 'unavailable'}",
        f"  {msg.links.ticket_label}: {msg.links.ticket_url or 'unavailable'}",
        f"  Alert: {msg.links.alert_url or 'unavailable'}",
    ]
    notes = msg.developer_notes
    if notes and msg.status in {"FAILED", "NEEDS_HUMAN"}:
        lines.extend(["", "For developers:", notes.developer_summary or ""])
        for g in notes.gaps[:5]:
            lines.append(f"  - gap: {g}")
        for s in notes.next_steps[:5]:
            lines.append(f"  - next: {s}")
        if notes.info_needed_to_close:
            lines.append(f"  - info needed: {notes.info_needed_to_close}")
    return "\n".join(lines)


def email_subject(msg: IncidentMessage) -> str:
    aid = msg.tracking_id or msg.alert_id or "AM"
    problem = (msg.problem or "incident").strip()
    if len(problem) > 70:
        problem = problem[:67] + "…"
    return f"[{aid}] {msg.status} · {problem}"
