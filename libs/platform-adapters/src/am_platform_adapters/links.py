"""Build Temporal / Grafana / ticket / alert URLs for incident messages."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any
from urllib.parse import urlparse


def _allowed_hosts() -> set[str]:
    raw = (os.getenv("LINK_ALLOWED_HOSTS") or "").strip()
    if raw:
        return {h.strip().lower() for h in raw.split(",") if h.strip()}
    return {
        "grafana.munish.org",
        "grafana.asrax.in",
        "openproject.asrax.in",
        "127.0.0.1",
        "localhost",
    }


def _host_ok(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    allowed = _allowed_hosts()
    return host in allowed or any(host.endswith("." + a) for a in allowed)


def ticket_browser_url(ticket_ref: str, *, url: str | None = None) -> str:
    if url and url.startswith("http") and _host_ok(url):
        return url
    ref = (ticket_ref or "").strip()
    if ref.startswith("op:wp:"):
        wp = ref.split(":")[-1]
        base = (os.getenv("OPENPROJECT_PUBLIC_URL") or "https://openproject.asrax.in").rstrip("/")
        return f"{base}/work_packages/{wp}"
    if ref.startswith("jira:"):
        key = ref.split(":", 1)[-1]
        base = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        if base:
            return f"{base}/browse/{key}"
    return url or ""


def ticket_number(ticket_ref: str) -> str:
    ref = (ticket_ref or "").strip()
    if ref.startswith("op:wp:"):
        return ref.split(":")[-1]
    if ref.startswith("jira:"):
        return ref.split(":", 1)[-1]
    return ref


def grafana_alert_url(generator_url: str | None) -> str:
    url = (generator_url or "").strip()
    if not url.startswith("http"):
        return ""
    return url if _host_ok(url) else ""


def grafana_tempo_trace_url(trace_id: str | None, *, from_: str = "now-6h", to: str = "now") -> str:
    tid = (trace_id or "").strip()
    if not tid:
        return ""
    base = (os.getenv("GRAFANA_EXTERNAL_URL") or "https://grafana.munish.org").rstrip("/")
    uid = (os.getenv("GRAFANA_TEMPO_DATASOURCE_UID") or "tempo").strip() or "tempo"
    org = (os.getenv("GRAFANA_ORG_ID") or "1").strip() or "1"
    panes = {
        "trace": {
            "datasource": uid,
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "tempo", "uid": uid},
                    "queryType": "traceql",
                    "query": tid,
                }
            ],
            "range": {"from": from_, "to": to},
        }
    }
    encoded = urllib.parse.quote(json.dumps(panes, separators=(",", ":")))
    return f"{base}/explore?orgId={org}&panes={encoded}&schemaVersion=1"


def temporal_ui_base(*, env: str | None = None) -> str:
    """Prefer env map for non-lab; never advertise localhost outside lab."""
    env_key = (env or "").strip().lower() or "lab"
    raw_map = (os.getenv("TEMPORAL_UI_URL_MAP") or "").strip()
    if raw_map:
        try:
            parsed = json.loads(raw_map)
            if isinstance(parsed, dict) and parsed.get(env_key):
                return str(parsed[env_key]).rstrip("/")
        except json.JSONDecodeError:
            pass
    explicit = (os.getenv("TEMPORAL_UI_EXTERNAL_URL") or "").strip().rstrip("/")
    if explicit:
        if env_key not in {"lab", "local", "unknown", ""} and (
            "127.0.0.1" in explicit or "localhost" in explicit
        ):
            return ""  # refuse publishing localhost to non-lab recipients
        return explicit
    if env_key in {"lab", "local", "unknown", ""}:
        return "http://127.0.0.1:8080"
    return ""


def temporal_workflow_url(
    workflow_id: str | None,
    *,
    run_id: str | None = None,
    env: str | None = None,
) -> str:
    wid = (workflow_id or "").strip()
    if not wid:
        return ""
    base = temporal_ui_base(env=env)
    if not base:
        return ""
    ns = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip() or "default"
    path = f"{base}/namespaces/{ns}/workflows/{urllib.parse.quote(wid, safe='')}"
    if run_id:
        path = f"{path}/{urllib.parse.quote(run_id, safe='')}"
    return path


def build_developer_links(
    *,
    ticket_ref: str = "",
    ticket_url: str | None = None,
    generator_url: str | None = None,
    trace_id: str | None = None,
    workflow_id: str | None = None,
    run_id: str | None = None,
    env: str | None = None,
    evidence_url: str | None = None,
    runbook_url: str | None = None,
) -> dict[str, Any]:
    from am_platform_ports.schemas.incident_message import DeveloperLinks

    t_url = ticket_browser_url(ticket_ref, url=ticket_url)
    label = "Jira" if (ticket_ref or "").startswith("jira:") else "OpenProject"
    return DeveloperLinks(
        temporal_url=temporal_workflow_url(workflow_id, run_id=run_id, env=env),
        grafana_trace_url=grafana_tempo_trace_url(trace_id),
        ticket_url=t_url,
        ticket_label=label,
        alert_url=grafana_alert_url(generator_url),
        evidence_url=(evidence_url or "").strip(),
        runbook_url=(runbook_url or "").strip(),
    ).model_dump()
