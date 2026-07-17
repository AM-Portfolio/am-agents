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


@activity.defn
async def create_and_assign_ticket(payload: dict[str, Any]) -> dict[str, str]:
    from am_platform_ports.agent_identity import (
        agent_prefix,
        ensure_env_label,
        title_with_env,
    )

    ports = get_ports()
    run_ref = payload["run_ref"]
    triage = dict(payload.get("triage") or {})
    alert = ensure_env_label(payload.get("alert") or {})
    labels = dict(triage.get("labels") or alert.get("labels") or {})
    env = str(labels.get("env") or alert.get("env") or "unknown")
    labels["env"] = env
    triage["labels"] = labels

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
    ports.tickets.assign(ticket_ref=ticket.ticket_ref, assignee_ref=hit.assignee_ref)
    ports.tickets.comment(
        ticket_ref=ticket.ticket_ref,
        body=f"{agent_prefix(env=env)} intake — assignee {hit.assignee_ref}",
    )
    ports.runs.update_run_status(
        run_ref=run_ref,
        status=RunStatus.RUNNING,
        summary={"ticket_ref": ticket.ticket_ref, "env": env},
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
        "assignee_ref": hit.assignee_ref,
        "channel_ref": hit.channel_ref or "cliq:lab",
        "env": env,
    }


@activity.defn
async def notify_ticket_created(payload: dict[str, Any]) -> dict[str, str]:
    from am_platform_ports.schemas.core import NotifyCard

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
    card = NotifyCard(
        event="ticket.created",
        title=payload.get("title") or "Ticket created",
        body=payload.get("body") or "",
        refs={
            "ticket_ref": payload["ticket_ref"],
            "run_ref": run_ref,
            "incident_ref": payload.get("incident_ref") or "",
            "env": env,
            "decision": "intake",
        },
    )
    notify_ref = ports.notifier.send_card(channel_ref=payload["channel_ref"], card=card)
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:notify",
            run_ref=run_ref,
            name="notify",
            status=StepStatus.PASSED,
            result_ref=notify_ref,
        )
    )
    return {"notify_ref": notify_ref}


@activity.defn
async def mark_run_status(payload: dict[str, Any]) -> None:
    ports = get_ports()
    ports.runs.update_run_status(
        run_ref=payload["run_ref"],
        status=RunStatus(payload["status"]),
        summary=payload.get("summary"),
    )
