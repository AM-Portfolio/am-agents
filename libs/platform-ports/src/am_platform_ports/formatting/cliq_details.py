"""Compact Cliq "View more" details page — Summary/Update + deep links."""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from am_platform_ports.agent_identity import agent_display_name
from am_platform_ports.schemas.incident_message import IncidentMessage

LOG = logging.getLogger("platform_ports.cliq_details")


def _e(value: str | None) -> str:
    return html.escape((value or "").strip())


def langfuse_public_url() -> str:
    return (
        os.getenv("LANGFUSE_PUBLIC_URL") or os.getenv("LANGFUSE_HOST") or ""
    ).strip().rstrip("/")


def _parse_ts(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = text.replace(" UTC", "+00:00").replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _fmt_ts(raw: str | None) -> str:
    dt = _parse_ts(raw)
    if not dt:
        return (raw or "").strip()
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def incident_timing(msg: IncidentMessage) -> dict[str, str]:
    """Received / resolution timestamps + time spent for Cliq table + View more."""
    received_raw = msg.started_at or msg.notified_at or ""
    resolved_raw = msg.ended_at or ""
    received_dt = _parse_ts(received_raw)
    resolved_dt = _parse_ts(resolved_raw)

    out: dict[str, str] = {}
    if received_raw:
        out["received"] = _fmt_ts(received_raw) or received_raw
    if resolved_raw:
        out["resolved"] = _fmt_ts(resolved_raw) or resolved_raw

    if received_dt and resolved_dt:
        out["time_spent"] = _fmt_duration((resolved_dt - received_dt).total_seconds())
    elif received_dt and (msg.status or "").upper() in {"RESOLVED", "FAILED"}:
        end = _parse_ts(msg.notified_at) or datetime.now(timezone.utc)
        out["time_spent"] = _fmt_duration((end - received_dt).total_seconds())
    return out


def _status_update(msg: IncidentMessage) -> str:
    status = (msg.status or "INVESTIGATING").strip().upper()
    update = (msg.success_summary or msg.reason or "").strip()
    if update:
        return update
    return {
        "INVESTIGATING": "Investigation started",
        "AUTO_INFRA": "Automated infrastructure remediation in progress",
        "NEEDS_HUMAN": "Human review required",
        "RESOLVED": "Incident resolved and verification passed",
        "FAILED": "Incident handling or verification failed",
    }.get(status, "Incident updated")


def _link_btn(label: str, url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    return (
        f'<a class="btn" href="{_e(url)}" target="_blank" rel="noopener">'
        f"{_e(label)}</a>"
    )


def render_cliq_view_more_html(msg: IncidentMessage) -> str:
    """Details page opened by Cliq View more (preview panel / new tab)."""
    aid = msg.tracking_id or msg.alert_id or "AM"
    status = msg.status or "INVESTIGATING"
    summary = (msg.problem or "").strip() or "Incident"
    update = _status_update(msg)
    links = msg.links
    lf = langfuse_public_url()
    timing = incident_timing(msg)

    link_btns = "".join(
        b
        for b in (
            _link_btn(links.ticket_label or "OpenProject", links.ticket_url),
            _link_btn("Open alert", links.alert_url),
            _link_btn("Temporal", links.temporal_url),
            _link_btn("Langfuse traces", lf),
            _link_btn("Runbook", links.runbook_url),
        )
        if b
    )

    meta_rows = []
    for label, value in (
        ("Status", status),
        ("Severity", msg.severity),
        ("Env", msg.env),
        ("App / NS", " / ".join(p for p in (msg.app, msg.namespace) if p) or ""),
        ("Owners", " · ".join(p for p in (msg.responsible, f"backup={msg.backup}" if msg.backup else "") if p)),
        ("Ticket", msg.ticket_number or msg.ticket_ref),
        ("Done by", msg.done_by or agent_display_name()),
        ("Received", timing.get("received", "")),
        ("Resolution", timing.get("resolved", "")),
        ("Time spent", timing.get("time_spent", "")),
    ):
        if value:
            meta_rows.append(
                f"<tr><th>{_e(label)}</th><td>{_e(str(value))}</td></tr>"
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>[{_e(aid)}] {_e(status)}</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
  .wrap {{ max-width: 720px; margin: 24px auto; padding: 0 16px; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }}
  h1 {{ font-size: 18px; margin: 0 0 16px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #64748b; margin: 18px 0 8px; }}
  p {{ margin: 0 0 8px; line-height: 1.45; white-space: pre-wrap; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; width: 28%; color: #64748b; padding: 8px 0; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
  td {{ padding: 8px 0; border-bottom: 1px solid #e2e8f0; }}
  .btns {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
  .btn {{ display: inline-block; padding: 10px 14px; border-radius: 8px; background: #0f766e;
         color: #fff !important; text-decoration: none; font-size: 13px; font-weight: 600; }}
</style>
</head>
<body>
<div class="wrap"><div class="card">
  <h1>[{_e(aid)}] {_e(status)}</h1>
  <h2>Summary</h2>
  <p>{_e(summary)}</p>
  <h2>Update</h2>
  <p>{_e(update)}</p>
  <h2>Links</h2>
  <div class="btns">{link_btns or "<p>No links available</p>"}</div>
  <h2>Details</h2>
  <table>{"".join(meta_rows)}</table>
</div></div>
</body>
</html>
"""


def _public_url_for_key(object_key: str, *, docs_url: str | None = None) -> str:
    """Prefer explicit public bases; localhost is OK (Cliq open.url runs in user browser)."""
    key = object_key.lstrip("/")
    for env_name in ("INCIDENT_VIEW_MORE_PUBLIC_BASE", "MINIO_PUBLIC_URL"):
        base = (os.getenv(env_name) or "").strip().rstrip("/")
        if base.startswith("http"):
            if env_name == "MINIO_PUBLIC_URL":
                bucket = (os.getenv("MINIO_BUCKET") or "agent-docs").strip()
                if base.rstrip("/").endswith(bucket):
                    return f"{base}/{key}"
                return f"{base}/{bucket}/{key}"
            return f"{base}/{key}"
    if docs_url and docs_url.startswith("http"):
        return docs_url
    return ""


def publish_cliq_view_more(
    msg: IncidentMessage,
    *,
    docs: Any | None = None,
) -> str:
    """
    Persist View-more HTML and return a browser URL when publicly reachable.
    Falls back to empty string (caller should use ticket URL).
    """
    html_body = render_cliq_view_more_html(msg)
    aid = re.sub(r"[^A-Za-z0-9._-]+", "-", (msg.tracking_id or msg.alert_id or "AM"))[:48]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_key = f"incident-cliq/{aid}/{stamp}-{msg.status.lower()}.html"

    dump = (os.getenv("INCIDENT_VIEW_MORE_DUMP_DIR") or os.getenv("INCIDENT_MAIL_DUMP_DIR") or "").strip()
    if dump:
        try:
            path = Path(dump) / "cliq_view_more" / f"{stamp}_{aid}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html_body, encoding="utf-8")
        except OSError as exc:
            LOG.warning("view-more dump failed: %s", exc)

    docs_url = ""
    if docs is not None:
        try:
            ref = docs.put(
                key=object_key,
                content=html_body.encode("utf-8"),
                content_type="text/html; charset=utf-8",
                meta={"tracking_id": aid, "kind": "cliq-view-more"},
            )
            docs_url = (getattr(ref, "url", None) or "") or ""
        except Exception as exc:  # noqa: BLE001
            LOG.warning("view-more docs put failed: %s", exc)

    return _public_url_for_key(object_key, docs_url=docs_url)
