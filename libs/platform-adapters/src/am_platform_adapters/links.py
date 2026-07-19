"""Build Temporal / Grafana / ticket / alert / Langfuse URLs for incident messages."""

from __future__ import annotations

import json
import os
import re
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
        "temporal.asrax.in",
        "langfuse.munish.org",
        "langfuse.asrax.in",
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


def _grafana_public_base() -> str:
    return (
        os.getenv("GRAFANA_EXTERNAL_URL") or "https://grafana.asrax.in"
    ).rstrip("/")


def normalize_grafana_url(url: str | None) -> str:
    """Fix truncated hosts like https://grafana./alerting/... from some relays."""
    raw = (url or "").strip()
    if not raw:
        return ""
    fixed = re.sub(
        r"^https?://grafana\.(?=/)",
        f"{_grafana_public_base()}",
        raw,
        count=1,
    )
    if fixed.startswith("http://grafana./") or fixed.startswith("https://grafana./"):
        fixed = _grafana_public_base() + fixed.split("grafana.", 1)[-1]
    # Prefer asrax public host when munish is interchangeable for deep links
    return fixed


def ticket_browser_url(ticket_ref: str, *, url: str | None = None) -> str:
    candidate = (url or "").strip()
    if candidate.startswith("http") and _host_ok(candidate):
        return candidate
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
    return candidate


def ticket_number(ticket_ref: str) -> str:
    ref = (ticket_ref or "").strip()
    if ref.startswith("op:wp:"):
        return ref.split(":")[-1]
    if ref.startswith("jira:"):
        return ref.split(":", 1)[-1]
    return ref


def grafana_alert_url(
    generator_url: str | None,
    *,
    alertname: str | None = None,
) -> str:
    """Prefer rule view URL; never use alerting/list search (matches rules, not firings)."""
    url = normalize_grafana_url(generator_url)
    if url.startswith("http") and _host_ok(url) and "/alerting/list" not in url:
        return url
    # Broken or list-only generator — deep-link firing groups by alertname
    name = (alertname or "").strip()
    base = _grafana_public_base()
    if name:
        return f"{base}/alerting/groups?search={urllib.parse.quote(name)}"
    if url.startswith("http") and _host_ok(url):
        return url
    return f"{base}/alerting/groups"


def grafana_tempo_trace_url(trace_id: str | None, *, from_: str = "now-6h", to: str = "now") -> str:
    tid = (trace_id or "").strip()
    if not tid:
        return ""
    base = _grafana_public_base()
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
    return "https://temporal.asrax.in"


def temporal_workflow_url(
    workflow_id: str | None,
    *,
    run_id: str | None = None,
    env: str | None = None,
) -> str:
    """Temporal UI deep link — include run id + /history when known."""
    wid = (workflow_id or "").strip()
    if not wid:
        return ""
    base = temporal_ui_base(env=env)
    if not base:
        return ""
    ns = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip() or "default"
    path = f"{base}/namespaces/{ns}/workflows/{urllib.parse.quote(wid, safe='')}"
    rid = (run_id or "").strip()
    if rid:
        path = f"{path}/{urllib.parse.quote(rid, safe='')}/history"
    return path


def langfuse_project_id() -> str:
    return (
        os.getenv("LANGFUSE_PROJECT_ID")
        or os.getenv("LANGFUSE_SUPPORT_AGENT_PROJECT_ID")
        or "cmsupportagent0001wx0dsa001"
    ).strip()


def langfuse_public_base() -> str:
    return (
        os.getenv("LANGFUSE_PUBLIC_URL")
        or os.getenv("LANGFUSE_HOST")
        or "https://langfuse.munish.org"
    ).rstrip("/")


def langfuse_trace_url(
    trace_id: str | None = None,
    *,
    tracking_id: str | None = None,
) -> str:
    """Project-scoped Langfuse URL (support-agent project)."""
    base = langfuse_public_base()
    project = langfuse_project_id()
    tid = (trace_id or "").strip()
    if tid:
        return f"{base}/project/{project}/traces/{urllib.parse.quote(tid, safe='')}"
    track = (tracking_id or "").strip()
    if track:
        return (
            f"{base}/project/{project}/traces"
            f"?search={urllib.parse.quote(track)}"
        )
    return f"{base}/project/{project}/traces"


def build_developer_links(
    *,
    ticket_ref: str = "",
    ticket_url: str | None = None,
    generator_url: str | None = None,
    alertname: str | None = None,
    trace_id: str | None = None,
    tracking_id: str | None = None,
    workflow_id: str | None = None,
    run_id: str | None = None,
    env: str | None = None,
    evidence_url: str | None = None,
    runbook_url: str | None = None,
    langfuse_trace_id: str | None = None,
) -> dict[str, Any]:
    from am_platform_ports.schemas.incident_message import DeveloperLinks

    t_url = ticket_browser_url(ticket_ref, url=ticket_url)
    label = "Jira" if (ticket_ref or "").startswith("jira:") else "OpenProject"
    lf_tid = (langfuse_trace_id or trace_id or "").strip()
    return DeveloperLinks(
        temporal_url=temporal_workflow_url(workflow_id, run_id=run_id, env=env),
        grafana_trace_url=grafana_tempo_trace_url(trace_id),
        ticket_url=t_url,
        ticket_label=label,
        alert_url=grafana_alert_url(generator_url, alertname=alertname),
        evidence_url=(evidence_url or "").strip(),
        runbook_url=(runbook_url or "").strip(),
    ).model_dump() | {
        # Extra for dashboards / lifecycle (DeveloperLinks may not have langfuse yet)
        "langfuse_url": langfuse_trace_url(lf_tid or None, tracking_id=tracking_id),
    }
