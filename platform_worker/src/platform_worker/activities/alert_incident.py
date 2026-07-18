"""AlertIncident activities — call ports only (no vendor types)."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from platform_worker.di import get_ports


@activity.defn
async def create_incident_run(payload: dict[str, Any]) -> dict[str, str]:
    """Intake: reuse gateway-created run_ref when present; else create."""
    ports = get_ports()
    existing = payload.get("run_ref")
    if existing:
        run = ports.runs.get_run(run_ref=str(existing))
        if run is None:
            raise KeyError(f"unknown run_ref: {existing}")
        return {"run_ref": run.run_ref}
    run = ports.runs.create_run(
        CreateRunRequest(
            kind=RunKind.ALERT_INCIDENT,
            status=RunStatus.ACCEPTED,
            incident_ref=payload.get("tracking_id") or payload.get("incident_ref"),
            workflow_id=payload.get("workflow_id"),
        )
    )
    return {"run_ref": run.run_ref}


@activity.defn
async def triage_alert(payload: dict[str, Any]) -> dict[str, Any]:
    from am_platform_ports.agent_identity import ensure_env_label

    ports = get_ports()
    run_ref = payload["run_ref"]
    alert = ensure_env_label(payload.get("alert") or {})
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:triage",
            run_ref=run_ref,
            name="triage",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    # Prompt key only — content from catalog/registry, not inline bodies
    _ = ports.prompts.get(prompt_key="triage.default")
    result = ports.triage.classify(alert_payload=alert)
    out = result.model_dump()
    # Ensure labels.env survives triage even if classifier drops it
    labels = dict(out.get("labels") or alert.get("labels") or {})
    labels["env"] = alert["labels"]["env"]
    out["labels"] = labels
    out["env"] = labels["env"]
    if not out.get("summary"):
        out["summary"] = alert.get("summary") or "Alert"
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:triage",
            run_ref=run_ref,
            name="triage",
            status=StepStatus.PASSED,
        )
    )
    return out


def _ticket_meta_from_summary(summary: dict[str, Any], *, env: str = "") -> dict[str, str]:
    return {
        "ticket_ref": str(summary.get("ticket_ref") or ""),
        "ticket_url": str(summary.get("ticket_url") or ""),
        "assignee_ref": str(summary.get("assignee_ref") or ""),
        "assignee_name": str(summary.get("assignee_name") or ""),
        "assignee_email": str(summary.get("assignee_email") or ""),
        "backup_name": str(summary.get("backup_name") or ""),
        "backup_email": str(summary.get("backup_email") or ""),
        "owner_source": str(summary.get("owner_source") or ""),
        "channel_ref": str(summary.get("channel_ref") or "cliq:lab"),
        "env": str(summary.get("env") or env or "unknown"),
        "reused": "1",
    }


@activity.defn
async def create_and_assign_ticket(payload: dict[str, Any]) -> dict[str, str]:
    """Idempotent ticket ensure: reuse run.ticket_ref / summary.ticket_ref on retry."""
    from am_platform_ports.agent_identity import (
        ensure_env_label,
        title_with_env,
    )
    from platform_worker.notify_incident import build_incident_message, comment_incident_phase

    ports = get_ports()
    run_ref = payload["run_ref"]
    triage = dict(payload.get("triage") or {})
    alert = ensure_env_label(payload.get("alert") or {})
    labels = dict(triage.get("labels") or alert.get("labels") or {})
    env = str(labels.get("env") or alert.get("env") or "unknown")
    labels["env"] = env
    triage["labels"] = labels
    tracking_id = str(payload.get("tracking_id") or payload.get("incident_ref") or "")
    workflow_id = str(payload.get("workflow_id") or "")

    existing = ports.runs.get_run(run_ref=run_ref)
    summary = dict((existing.summary if existing else None) or {})
    existing_ticket = str(
        (existing.ticket_ref if existing else None) or summary.get("ticket_ref") or ""
    ).strip()
    if existing_ticket:
        # Retry-safe: never create a second ticket after create already succeeded
        meta = _ticket_meta_from_summary(summary, env=env)
        meta["ticket_ref"] = existing_ticket
        if not meta.get("ticket_url"):
            meta["ticket_url"] = str(summary.get("ticket_url") or "")
        return meta

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:ticket",
            run_ref=run_ref,
            name="ticket",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    hit = ports.directory.resolve(labels=labels, priority=triage.get("priority") or "P3")
    title = title_with_env(env, triage.get("summary") or alert.get("summary") or "Alert")
    ticket = ports.tickets.create(
        title=title,
        description=str(alert),
        priority=triage.get("priority") or "P3",
        labels=labels,
    )
    # Persist ticket_ref immediately so a timeout after create cannot spawn a duplicate
    early_summary = {
        **summary,
        "ticket_ref": ticket.ticket_ref,
        "ticket_url": ticket.url or "",
        "env": env,
        "assignee_ref": hit.assignee_ref,
        "assignee_name": str(getattr(hit, "assignee_name", None) or ""),
        "assignee_email": str(getattr(hit, "assignee_email", None) or ""),
        "backup_name": str(getattr(hit, "backup_name", None) or ""),
        "backup_email": str(getattr(hit, "backup_email", None) or ""),
        "owner_source": str(getattr(hit, "owner_source", None) or ""),
        "channel_ref": hit.channel_ref or "cliq:lab",
    }
    ports.runs.update_run_status(
        run_ref=run_ref,
        status=RunStatus.RUNNING,
        summary=early_summary,
    )

    ports.tickets.assign(ticket_ref=ticket.ticket_ref, assignee_ref=hit.assignee_ref)

    msg = build_incident_message(
        status="INVESTIGATING",
        tracking_id=tracking_id,
        alert=alert,
        ticket_ref=ticket.ticket_ref,
        ticket_url=ticket.url,
        env=env,
        reason="Ticket created and assigned — investigation started.",
        decision="intake",
        run_ref=run_ref,
        workflow_id=workflow_id,
        responsible=str(getattr(hit, "assignee_name", None) or hit.assignee_ref),
        backup=str(getattr(hit, "backup_name", None) or ""),
        owner_source=str(getattr(hit, "owner_source", None) or ""),
        assignee_email=str(getattr(hit, "assignee_email", None) or ""),
        backup_email=str(getattr(hit, "backup_email", None) or ""),
        done_by="IT-Support-agent",
    )
    comment_incident_phase(
        ports,
        msg=msg,
        phase="INTAKE",
        extras=[
            f"Assignee ref: {hit.assignee_ref}",
            f"Channel: {hit.channel_ref or 'cliq:lab'}",
            f"Ticket URL: {ticket.url or 'n/a'}",
            f"checkpoint_key=incident:{run_ref}:phase:intake",
        ],
    )
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:ticket",
            run_ref=run_ref,
            name="ticket",
            status=StepStatus.PASSED,
            result_ref=ticket.ticket_ref,
        )
    )
    return {
        "ticket_ref": ticket.ticket_ref,
        "ticket_url": ticket.url or "",
        "assignee_ref": hit.assignee_ref,
        "assignee_name": str(getattr(hit, "assignee_name", None) or ""),
        "assignee_email": str(getattr(hit, "assignee_email", None) or ""),
        "backup_name": str(getattr(hit, "backup_name", None) or ""),
        "backup_email": str(getattr(hit, "backup_email", None) or ""),
        "owner_source": str(getattr(hit, "owner_source", None) or ""),
        "channel_ref": hit.channel_ref or "cliq:lab",
        "env": env,
        "reused": "0",
    }


@activity.defn
async def notify_ticket_created(payload: dict[str, Any]) -> dict[str, str]:
    from platform_worker.notify_incident import build_incident_message, notify_incident_channels

    ports = get_ports()
    run_ref = payload["run_ref"]
    env = str(payload.get("env") or "")
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:notify",
            run_ref=run_ref,
            name="notify",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    msg = build_incident_message(
        status="INVESTIGATING",
        tracking_id=str(payload.get("tracking_id") or payload.get("incident_ref") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=payload["ticket_ref"],
        ticket_url=payload.get("ticket_url"),
        env=env,
        reason="Ticket created and assigned — investigation started.",
        decision="intake",
        run_ref=run_ref,
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or payload.get("assignee_ref") or ""),
        backup=str(payload.get("backup_name") or ""),
        owner_source=str(payload.get("owner_source") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        done_by="IT-Support-agent",
    )
    # Avoid duplicate OP comment — intake already commented
    result = notify_incident_channels(
        ports,
        msg=msg,
        channel_ref=payload["channel_ref"],
        also_ticket_comment=False,
    )
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:notify",
            run_ref=run_ref,
            name="notify",
            status=StepStatus.PASSED,
            result_ref=result.get("cliq") or "ok",
        )
    )
    return {"notify_ref": result.get("cliq") or "", "mail_ref": result.get("mail") or ""}


@activity.defn
async def post_incident_phase(payload: dict[str, Any]) -> dict[str, str]:
    """Post a soft phase checkpoint to Jira/OP so prior phases survive later failures."""
    from platform_worker.notify_incident import build_incident_message, comment_incident_phase

    ports = get_ports()
    phase = str(payload.get("phase") or "UPDATE").upper()
    status = str(payload.get("status") or "INVESTIGATING")
    if status not in {"INVESTIGATING", "AUTO_INFRA", "NEEDS_HUMAN", "RESOLVED", "FAILED"}:
        status = "INVESTIGATING"
    msg = build_incident_message(
        status=status,  # type: ignore[arg-type]
        tracking_id=str(payload.get("tracking_id") or payload.get("incident_ref") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=str(payload.get("ticket_ref") or ""),
        ticket_url=payload.get("ticket_url"),
        env=str(payload.get("env") or ""),
        reason=str(payload.get("reason") or ""),
        success_summary=str(payload.get("success_summary") or ""),
        decision=str(payload.get("decision") or ""),
        run_ref=str(payload.get("run_ref") or ""),
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        evidence_url=str(payload.get("evidence_url") or ""),
        done_by="IT-Support-agent",
    )
    extras = payload.get("extras")
    if not isinstance(extras, list):
        extras = [str(extras)] if extras else None
    result = comment_incident_phase(ports, msg=msg, phase=phase, extras=extras)
    return {"ticket_comment": result, "phase": phase}


@activity.defn
async def mark_run_status(payload: dict[str, Any]) -> None:
    ports = get_ports()
    ports.runs.update_run_status(
        run_ref=payload["run_ref"],
        status=RunStatus(payload["status"]),
        summary=payload.get("summary"),
    )
