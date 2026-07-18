"""Lifecycle snapshot helpers for ticket/agent/final status dashboards."""

from __future__ import annotations

from typing import Any


_PHASE_TO_AGENT_STATUS = {
    "init": "starting",
    "check_parity": "investigating",
    "gated": "gated",
    "normalize_alert": "investigating",
    "retrieve_memory": "investigating",
    "query_evidence": "investigating",
    "intelligence_gate": "investigating",
    "not_confirmed": "not_confirmed",
    "plan_investigation": "investigating",
    "propose_known_fix": "investigating",
    "human_handoff_complete": "hitl_waiting",
    "awaiting_resolved_or_refired": "awaiting_resolution",
    "refired_refresh": "investigating",
    "verify_recovery": "verifying",
    "recovered": "recovered",
    "parse_alert_feedback": "feedback",
    "continue_as_new": "continuing",
}

_DOMAIN_TO_FINAL = {
    "recovered": "recovered",
    "closed": "closed",
    "human_required": "human_required",
    "not_confirmed": "not_confirmed",
    "failed": "failed",
    "gated": "gated",
    "partial": "partial",
}


def agent_status_for_phase(phase: str) -> str:
    key = (phase or "").strip()
    return _PHASE_TO_AGENT_STATUS.get(key, key or "unknown")


def final_status_for_domain(domain_status: str | None) -> str:
    if not domain_status:
        return "open"
    return _DOMAIN_TO_FINAL.get(domain_status.strip().lower(), "open")


def familiar_type_from_alert(alert: dict[str, Any] | None) -> tuple[str, str]:
    """Return (familiar_type, fingerprint) from alert payload/labels."""
    body = dict(alert or {})
    labels = dict(body.get("labels") or {})
    alertname = str(
        labels.get("alertname")
        or body.get("alertname")
        or body.get("name")
        or "unknown"
    ).strip()
    service = str(
        labels.get("service")
        or labels.get("app")
        or labels.get("application")
        or body.get("service")
        or ""
    ).strip()
    namespace = str(
        labels.get("namespace")
        or body.get("namespace")
        or ""
    ).strip()
    fingerprint = str(
        body.get("fingerprint")
        or labels.get("fingerprint")
        or ""
    ).strip()
    if not fingerprint:
        fingerprint = "|".join(p for p in (alertname, service, namespace) if p)
    familiar = "|".join(p for p in (alertname, service or "-", namespace or "-") if p)
    return familiar or "unknown", fingerprint or familiar or "unknown"


def ticket_ref_from_work_item(work_item: Any) -> str:
    if not isinstance(work_item, dict):
        return ""
    return str(work_item.get("work_item_ref") or work_item.get("id") or "").strip()


def condense_activities(steps: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, step in (steps or {}).items():
        if not isinstance(step, dict):
            out[str(name)] = {"ok": True, "detail": str(step)[:120]}
            continue
        err = step.get("error") or step.get("err") or ""
        ok = bool(step.get("ok", True)) and not err
        out[str(name)] = {
            "ok": ok,
            "phase": str(step.get("phase") or "")[:64],
            "error": str(err)[:200] if err else "",
        }
    return out


def build_lifecycle_summary(
    *,
    phase: str,
    steps: dict[str, Any] | None,
    state: dict[str, Any] | None,
    domain_status: str | None = None,
    final_status: str | None = None,
) -> dict[str, Any]:
    st = dict(state or {})
    alert = st.get("alert") if isinstance(st.get("alert"), dict) else {}
    labels = dict(alert.get("labels") or {})
    familiar, fingerprint = familiar_type_from_alert(alert)
    work_item = st.get("work_item") if isinstance(st.get("work_item"), dict) else {}
    owner = st.get("owner") if isinstance(st.get("owner"), dict) else {}
    ticket_ref = ticket_ref_from_work_item(work_item)
    assignee_ref = str(
        owner.get("assignee_ref") or work_item.get("assignee_ref") or ""
    ).strip()
    assignee_name = str(
        owner.get("assignee_name") or work_item.get("assignee_name") or ""
    ).strip()
    assignee_email = str(
        owner.get("assignee_email") or work_item.get("assignee_email") or ""
    ).strip()
    side = dict(st.get("side_effects") or {})
    known = st.get("known_fix")
    known_id = ""
    if isinstance(known, dict):
        known_id = str(known.get("candidate_id") or known.get("id") or "")[:120]
    fs = final_status or final_status_for_domain(domain_status)

    tracking_id = str(st.get("tracking_id") or "").strip()
    workflow_id = str(
        st.get("workflow_id") or (f"alert-incident-{tracking_id}" if tracking_id else "")
    ).strip()
    temporal_run_id = str(
        st.get("temporal_run_id") or st.get("run_id") or ""
    ).strip()
    trace_id = str(
        alert.get("trace_id") or labels.get("trace_id") or st.get("trace_id") or ""
    ).strip()
    langfuse_trace_id = str(
        st.get("langfuse_trace_id") or alert.get("langfuse_trace_id") or ""
    ).strip()
    generator_url = str(
        alert.get("generator_url")
        or alert.get("generatorURL")
        or labels.get("generatorURL")
        or ""
    ).strip()
    alertname = str(
        labels.get("alertname") or alert.get("alertname") or alert.get("name") or ""
    ).strip()
    ticket_url = str(work_item.get("url") or st.get("ticket_url") or "").strip()

    links: dict[str, Any] = {}
    try:
        from am_platform_adapters.links import (
            build_developer_links,
            ticket_browser_url,
        )

        links = build_developer_links(
            ticket_ref=ticket_ref,
            ticket_url=ticket_url or None,
            generator_url=generator_url or None,
            alertname=alertname or None,
            trace_id=trace_id or None,
            tracking_id=tracking_id or None,
            workflow_id=workflow_id or None,
            run_id=temporal_run_id or None,
            env=str(alert.get("env") or labels.get("env") or ""),
            langfuse_trace_id=langfuse_trace_id or None,
        )
        if not ticket_url:
            ticket_url = str(links.get("ticket_url") or ticket_browser_url(ticket_ref) or "")
    except Exception:  # noqa: BLE001 — links must not break lifecycle persist
        links = {}

    return {
        "phase": phase or "",
        "agent_status": agent_status_for_phase(phase),
        "final_status": fs,
        "ticket_ref": ticket_ref,
        "ticket_url": ticket_url,
        "ticket_status": str(side.get("ticket_status") or ("created" if ticket_ref else "none")),
        "assignee_ref": assignee_ref,
        "assignee_name": assignee_name,
        "assignee_email": assignee_email,
        "chat_sent": str(side.get("chat_notify") or "skipped"),
        "mail_sent": str(side.get("mail_notify") or "n/a"),
        "side_effects": side,
        "activities": condense_activities(steps),
        "familiar_type": familiar,
        "alert_fingerprint": fingerprint,
        "alertname": alertname,
        "generator_url": generator_url,
        "trace_id": trace_id,
        "langfuse_trace_id": langfuse_trace_id,
        "tracking_id": tracking_id,
        "workflow_id": workflow_id,
        "temporal_run_id": temporal_run_id,
        "temporal_url": str(links.get("temporal_url") or ""),
        "alert_url": str(links.get("alert_url") or ""),
        "langfuse_url": str(links.get("langfuse_url") or ""),
        "grafana_trace_url": str(links.get("grafana_trace_url") or ""),
        "similar_incident_ids": list(st.get("similar_incident_ids") or [])[:10],
        "known_fix": known_id,
        "hitl_state": (
            "requested"
            if st.get("human_required")
            else str((st.get("hitl") or {}).get("state") or "")
        ),
        "approval_purpose": str(
            (st.get("human_required") or {}).get("approval_purpose") or ""
        ),
        "solved": fs in {"recovered", "closed"},
    }


__all__ = [
    "agent_status_for_phase",
    "build_lifecycle_summary",
    "condense_activities",
    "familiar_type_from_alert",
    "final_status_for_domain",
    "ticket_ref_from_work_item",
]
