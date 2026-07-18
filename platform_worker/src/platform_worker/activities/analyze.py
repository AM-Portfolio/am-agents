"""Analyze / route / handoff activities for AlertIncident LLM path."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from temporalio import activity

from am_platform_ports.policy.incident_actions import enforce_decision
from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.incident import IncidentDecision
from am_platform_ports.schemas.run import UpsertStepRequest
from platform_worker.di import get_ports


def _render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for key, val in variables.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out


def _parse_decision_json(raw: str) -> IncidentDecision:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return IncidentDecision.model_validate(json.loads(text))


def analysis_enabled() -> bool:
    return os.getenv("ALERT_ANALYSIS", "llm").strip().lower() in {"llm", "1", "true", "yes", "on"}


@activity.defn
async def analyze_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM analyze → policy enforce → IncidentDecision dict."""
    from am_platform_ports.agent_identity import ensure_env_label, normalize_alert_env

    ports = get_ports()
    run_ref = payload["run_ref"]
    alert = ports.redactor.scrub(payload=payload.get("alert") or {})
    if not isinstance(alert, dict):
        alert = {}
    alert = ensure_env_label(alert)
    env = normalize_alert_env(alert)

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:analyze",
            run_ref=run_ref,
            name="incident.analyze",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )

    prompt = ports.prompts.get(prompt_key="incident.analyze")
    variables = {
        "summary": alert.get("summary") or "",
        "priority": alert.get("priority") or "",
        "labels": json.dumps(alert.get("labels") or {}),
        "annotations": json.dumps(alert.get("annotations") or {}),
        "fingerprint": alert.get("fingerprint") or "",
        "generator_url": alert.get("generator_url") or "",
        "group_size": alert.get("group_size") or 1,
        "trace_id": alert.get("trace_id") or "",
        "span_id": alert.get("span_id") or "",
        "system": prompt.get("system") or "",
        "user": _render(str(prompt.get("user") or ""), {
            "summary": alert.get("summary") or "",
            "priority": alert.get("priority") or "",
            "labels": json.dumps(alert.get("labels") or {}),
            "annotations": json.dumps(alert.get("annotations") or {}),
            "fingerprint": alert.get("fingerprint") or "",
            "generator_url": alert.get("generator_url") or "",
            "group_size": alert.get("group_size") or 1,
            "trace_id": alert.get("trace_id") or "",
            "span_id": alert.get("span_id") or "",
        }),
    }
    raw = ports.llm.complete(prompt_key="incident.analyze", variables=variables)
    decision = enforce_decision(_parse_decision_json(raw), env=env)

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:analyze",
            run_ref=run_ref,
            name="incident.analyze",
            status=StepStatus.PASSED,
            result_ref=decision.decision,
        )
    )
    out = decision.model_dump()
    out["env"] = env
    return out


@activity.defn
async def apply_ticket_decision(payload: dict[str, Any]) -> dict[str, str]:
    """Phase DECISION comment on Jira/OP + optional Cliq/mail for needs_human."""
    from am_platform_ports.agent_identity import normalize_alert_env
    from am_platform_ports.schemas.incident_message import DeveloperNotes
    from platform_worker.notify_incident import (
        build_incident_message,
        comment_incident_phase,
    )

    ports = get_ports()
    run_ref = payload["run_ref"]
    ticket_ref = payload["ticket_ref"]
    decision = IncidentDecision.model_validate(payload["decision"])
    env = str(payload.get("env") or normalize_alert_env(labels={"env": payload.get("env") or ""}))
    if env == "unknown" and payload.get("decision", {}).get("env"):
        env = str(payload["decision"]["env"])

    body = decision.ticket_update or decision.rationale or decision.decision
    status = {
        "needs_human": "NEEDS_HUMAN",
        "auto_infra": "AUTO_INFRA",
        "ignore": "RESOLVED",
    }.get(decision.decision, "INVESTIGATING")

    notes = None
    if decision.decision == "needs_human":
        notes = DeveloperNotes(
            developer_summary=decision.rationale or body,
            next_steps=["Review ticket and alert context", "Confirm code vs infra change"],
            info_needed_to_close="Owner confirmation of fix or escalate to development",
            move_to_development=True,
            move_to_development_why="Decision routed to needs_human (code/service change likely)",
            source="template",
        )

    msg = build_incident_message(
        status=status,  # type: ignore[arg-type]
        tracking_id=str(payload.get("tracking_id") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=ticket_ref,
        ticket_url=payload.get("ticket_url"),
        env=env,
        reason=decision.rationale or body,
        decision=decision.decision,
        run_ref=run_ref,
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        developer_notes=notes,
        done_by="IT-Support-agent",
    )
    # Always persist decision on ticket (Jira or OP) before chat/mail
    comment_incident_phase(
        ports,
        msg=msg,
        phase="DECISION",
        extras=[
            f"confidence={decision.confidence}",
            f"handoff_agent={decision.handoff_agent or 'n/a'}",
            f"proposed_actions={json.dumps([a.model_dump() for a in decision.proposed_actions], default=str)[:1500]}",
            f"ticket_update={decision.ticket_update or ''}",
        ],
    )

    if decision.decision == "needs_human":
        # Cliq/mail posted by workflow activities post_cliq_update + send_incident_mail
        ports.runs.update_run_status(
            run_ref=run_ref,
            status=RunStatus.NEEDS_HUMAN,
            summary={"decision": decision.decision, "ticket_ref": ticket_ref, "env": env},
        )
    elif decision.decision == "ignore":
        ports.runs.update_run_status(
            run_ref=run_ref,
            status=RunStatus.CANCELLED,
            summary={
                "decision": "ignore",
                "rationale": decision.rationale,
                "ticket_ref": ticket_ref,
                "env": env,
            },
        )
    elif decision.decision == "auto_infra":
        # Checkpoint only — handoff/verify add later phases
        ports.runs.update_run_status(
            run_ref=run_ref,
            status=RunStatus.RUNNING,
            summary={"decision": decision.decision, "ticket_ref": ticket_ref, "env": env},
        )
    return {"ok": "1", "env": env}


def _handoff_phase_msg(payload: dict[str, Any], *, status: str, reason: str):
    from platform_worker.notify_incident import build_incident_message

    return build_incident_message(
        status=status,  # type: ignore[arg-type]
        tracking_id=str(payload.get("tracking_id") or payload.get("incident_ref") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=str(payload.get("ticket_ref") or ""),
        ticket_url=payload.get("ticket_url"),
        env=str(payload.get("env") or ""),
        reason=reason,
        decision="auto_infra",
        run_ref=str(payload.get("run_ref") or ""),
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        done_by="IT-Support-agent",
    )


def _find_step(ports: Any, *, run_ref: str, name: str):
    for step in ports.runs.list_steps(run_ref=run_ref):
        if step.name == name:
            return step
    return None


@activity.defn
async def create_infra_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Create infra handoff once; short-circuit if handoff step already has result_ref."""
    from platform_worker.notify_incident import comment_incident_phase

    ports = get_ports()
    run_ref = payload["run_ref"]
    decision = IncidentDecision.model_validate(payload["decision"])
    ticket_ref = str(payload.get("ticket_ref") or "")
    action_names = [a.tool_name for a in decision.proposed_actions]
    step_name = "incident.handoff"
    step_ref = f"{run_ref}:handoff"

    existing = _find_step(ports, run_ref=run_ref, name=step_name)
    if existing and existing.status == StepStatus.PASSED and existing.result_ref:
        return {
            "ok": True,
            "handoff_ref": existing.result_ref,
            "reused": True,
            "actions": action_names,
        }

    if ticket_ref:
        comment_incident_phase(
            ports,
            msg=_handoff_phase_msg(
                payload,
                status="AUTO_INFRA",
                reason="Starting infra handoff and allowlisted remediation.",
            ),
            phase="HANDOFF",
            extras=[
                f"Target agent: {decision.handoff_agent or 'kagent_infra'}",
                f"Proposed actions: {', '.join(action_names) or 'none'}",
                f"Rationale: {(decision.rationale or '')[:800]}",
                f"checkpoint_key=incident:{run_ref}:phase:handoff_start",
            ],
        )

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=step_ref,
            run_ref=run_ref,
            name=step_name,
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    try:
        handoff_ref = ports.handoff.handoff(
            from_run_ref=run_ref,
            to_kind=RunKind.HANDOFF.value,
            depth=1,
            context={
                "agent": decision.handoff_agent or "kagent_infra",
                "actions": [a.model_dump() for a in decision.proposed_actions],
            },
        )
    except Exception as exc:  # noqa: BLE001
        reason = f"handoff failed: {exc}"[:400]
        if ticket_ref:
            comment_incident_phase(
                ports,
                msg=_handoff_phase_msg(payload, status="FAILED", reason=reason),
                phase="HANDOFF",
                extras=["Handoff failed before tools ran.", f"error={reason}"],
            )
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=step_ref,
                run_ref=run_ref,
                name=step_name,
                status=StepStatus.FAILED,
                result_ref="handoff_failed",
            )
        )
        return {
            "ok": False,
            "handoff_ref": None,
            "reused": False,
            "failure_reason": reason,
            "actions": action_names,
        }

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=step_ref,
            run_ref=run_ref,
            name=step_name,
            status=StepStatus.PASSED,
            result_ref=handoff_ref,
        )
    )
    return {
        "ok": True,
        "handoff_ref": handoff_ref,
        "reused": False,
        "actions": action_names,
    }


@activity.defn
async def execute_infra_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one allowlisted infra action; short-circuit if step already PASSED."""
    from platform_worker.notify_incident import comment_incident_phase

    ports = get_ports()
    run_ref = payload["run_ref"]
    tool_name = str(payload.get("tool_name") or "")
    args = dict(payload.get("args") or {})
    index = int(payload.get("index") or 0)
    operation_key = str(
        payload.get("operation_key") or f"incident:{run_ref}:action:{index}:{tool_name}"
    )
    step_name = f"infra.action.{index}.{tool_name}"
    step_ref = f"{run_ref}:{step_name}"
    ticket_ref = str(payload.get("ticket_ref") or "")

    existing = _find_step(ports, run_ref=run_ref, name=step_name)
    if existing and existing.status == StepStatus.PASSED and existing.result_ref:
        return {
            "ok": True,
            "tool_name": tool_name,
            "work_ref": existing.result_ref,
            "reused": True,
            "operation_key": operation_key,
            "error": None,
        }

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=step_ref,
            run_ref=run_ref,
            name=step_name,
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    try:
        plan = ports.infra.plan(
            incident_ref=payload.get("incident_ref") or "",
            context={
                "ticket_ref": ticket_ref,
                "proposed_actions": [{"tool_name": tool_name, "args": args}],
                "alert": payload.get("alert") or {},
                "operation_key": operation_key,
            },
        )
        done = ports.infra.execute(plan=plan)
        work_ref = done.work_ref
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=step_ref,
                run_ref=run_ref,
                name=step_name,
                status=StepStatus.PASSED,
                result_ref=work_ref,
            )
        )
        return {
            "ok": True,
            "tool_name": tool_name,
            "work_ref": work_ref,
            "actions_ran": list(done.actions_ran or [tool_name]),
            "reused": False,
            "operation_key": operation_key,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        reason = f"tool {tool_name} failed: {exc}"[:400]
        if ticket_ref:
            comment_incident_phase(
                ports,
                msg=_handoff_phase_msg(payload, status="FAILED", reason=reason),
                phase="HANDOFF",
                extras=[
                    f"operation_key={operation_key}",
                    f"Actions completed before failure may remain on prior steps.",
                ],
            )
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=step_ref,
                run_ref=run_ref,
                name=step_name,
                status=StepStatus.FAILED,
                result_ref=tool_name,
            )
        )
        return {
            "ok": False,
            "tool_name": tool_name,
            "work_ref": None,
            "actions_ran": [],
            "reused": False,
            "operation_key": operation_key,
            "error": reason,
            "failure_reason": reason,
        }


@activity.defn
async def handoff_infra_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper: handoff once then execute each action."""
    from platform_worker.notify_incident import comment_incident_phase

    decision = IncidentDecision.model_validate(payload["decision"])
    attempts: list[dict[str, Any]] = []
    actions_ran: list[str] = []

    handoff = await create_infra_handoff(payload)
    if not handoff.get("ok", True):
        reason = str(handoff.get("failure_reason") or "handoff failed")
        attempts.append({"step": "handoff", "status": "failed", "error": reason})
        return {
            "ok": False,
            "handoff_ref": None,
            "actions_ran": [],
            "attempts": attempts,
            "failure_reason": reason,
            "summary": reason,
        }
    handoff_ref = handoff.get("handoff_ref")
    attempts.append(
        {
            "step": "handoff",
            "status": "ok",
            "handoff_ref": handoff_ref,
            "reused": handoff.get("reused"),
        }
    )

    for index, action in enumerate(decision.proposed_actions):
        out = await execute_infra_action(
            {
                **payload,
                "tool_name": action.tool_name,
                "args": action.args or {},
                "index": index,
                "operation_key": f"incident:{payload['run_ref']}:action:{index}:{action.tool_name}",
            }
        )
        if out.get("ok"):
            actions_ran.extend(out.get("actions_ran") or [action.tool_name])
            attempts.append(
                {
                    "step": "tool",
                    "tool_name": action.tool_name,
                    "status": "ok",
                    "work_ref": out.get("work_ref"),
                    "reused": out.get("reused"),
                    "operation_key": out.get("operation_key"),
                }
            )
            continue
        reason = str(out.get("failure_reason") or out.get("error") or "tool failed")
        attempts.append(
            {
                "step": "tool",
                "tool_name": action.tool_name,
                "status": "failed",
                "error": reason,
                "operation_key": out.get("operation_key"),
            }
        )
        return {
            "ok": False,
            "handoff_ref": handoff_ref,
            "actions_ran": actions_ran,
            "attempts": attempts,
            "failure_reason": reason,
            "summary": reason,
        }

    summary = f"work_done actions={','.join(actions_ran)}"
    ticket_ref = str(payload.get("ticket_ref") or "")
    if ticket_ref:
        ports = get_ports()
        comment_incident_phase(
            ports,
            msg=_handoff_phase_msg(
                payload,
                status="AUTO_INFRA",
                reason=summary,
            ),
            phase="HANDOFF",
            extras=[
                f"handoff_ref={handoff_ref}",
                f"actions_ran={', '.join(actions_ran) or 'none'}",
                f"checkpoint_key=incident:{payload['run_ref']}:phase:handoff_result",
            ],
        )
    return {
        "ok": True,
        "handoff_ref": handoff_ref,
        "actions_ran": actions_ran,
        "attempts": attempts,
        "failure_reason": None,
        "summary": summary,
    }


@activity.defn
async def escalate_unsolved(payload: dict[str, Any]) -> dict[str, str]:
    """Document attempts + why unsolved; ticket comment + RunStore → needs_human.

    Cliq/mail posted by workflow activities post_cliq_update + send_incident_mail.
    """
    from am_platform_ports.schemas.incident_message import DeveloperNotes
    from platform_worker.notify_incident import (
        build_incident_message,
        comment_incident_phase,
    )

    ports = get_ports()
    run_ref = payload["run_ref"]
    ticket_ref = payload["ticket_ref"]
    env = str(payload.get("env") or "")
    decision = IncidentDecision.model_validate(payload.get("decision") or {"decision": "auto_infra"})
    attempts = payload.get("attempts") or []
    failure_reason = str(payload.get("failure_reason") or "unknown")
    verify_status = str(payload.get("verify_status") or "")
    verify_reason = str(payload.get("verify_reason") or failure_reason)
    verify_evidence = payload.get("verify_evidence") or []
    extra = str(payload.get("extra") or "")

    prompt = ports.prompts.get(prompt_key="incident.escalate_unsolved")
    variables = {
        "system": prompt.get("system") or "",
        "user": _render(
            str(prompt.get("user") or ""),
            {
                "decision": decision.decision,
                "rationale": decision.rationale,
                "attempts": json.dumps(attempts, default=str),
                "failure_reason": failure_reason,
                "verify_status": verify_status,
                "extra": extra,
            },
        ),
        "decision": decision.decision,
        "rationale": decision.rationale,
        "attempts": json.dumps(attempts, default=str),
        "failure_reason": failure_reason,
        "verify_status": verify_status,
        "extra": extra,
    }
    note = ports.llm.complete(prompt_key="incident.escalate_unsolved", variables=variables)
    note = ports.redactor.scrub(payload={"note": note})
    if isinstance(note, dict):
        note = str(note.get("note") or note)

    notes = DeveloperNotes(
        developer_summary=str(note)[:400] if note else failure_reason,
        gaps=[
            g
            for g in (
                f"verify_status={verify_status}" if verify_status else "",
                "trace may be missing" if not (payload.get("alert") or {}).get("trace_id") else "",
            )
            if g
        ],
        next_steps=[
            "Open Temporal workflow from Developer Links",
            "Review verify evidence on the ticket",
            "Confirm whether this needs a code change vs infra fix",
        ],
        info_needed_to_close="Owner confirmation of remediation or move to development",
        move_to_development="code" in failure_reason.lower() or "app" in (decision.rationale or "").lower(),
        move_to_development_why=failure_reason[:200],
        source="llm" if note else "template",
    )
    msg = build_incident_message(
        status="FAILED",
        tracking_id=str(payload.get("tracking_id") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=ticket_ref,
        ticket_url=payload.get("ticket_url"),
        env=env,
        reason=verify_reason or failure_reason,
        decision="unsolved",
        run_ref=run_ref,
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        evidence_url=str(payload.get("evidence_url") or ""),
        developer_notes=notes,
        done_by="IT-Support-agent",
        ended=True,
    )
    # Soft phase comment — prior INTAKE/DECISION/HANDOFF/VERIFY stay on ticket
    comment_incident_phase(
        ports,
        msg=msg,
        phase="ESCALATE",
        extras=[
            f"Accepted as: {decision.decision}",
            f"Why accepted: {decision.rationale or '—'}",
            f"Why not solved: {failure_reason}",
            f"Verify: {verify_status or 'n/a'}",
            f"What was tried: {json.dumps(attempts, default=str)[:2500]}",
            f"Verify evidence: {json.dumps(verify_evidence, default=str)[:2500]}"
            if verify_evidence
            else "",
            f"Extra: {extra}" if extra else "",
            f"Handoff note: {note}" if note else "",
        ],
    )
    # Cliq/mail posted by workflow activities post_cliq_update + send_incident_mail
    ports.runs.update_run_status(
        run_ref=run_ref,
        status=RunStatus.NEEDS_HUMAN,
        summary={
            "decision": decision.decision,
            "escalated": True,
            "failure_reason": failure_reason,
            "attempts": attempts,
            "verify_status": verify_status or None,
            "ticket_ref": ticket_ref,
            "env": env or None,
        },
    )
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:escalate_unsolved",
            run_ref=run_ref,
            name="incident.escalate_unsolved",
            status=StepStatus.PASSED,
            result_ref="needs_human",
        )
    )
    return {"note": str(note), "status": "needs_human"}


@activity.defn
async def write_resolution_note(payload: dict[str, Any]) -> dict[str, str]:
    from platform_worker.notify_incident import build_incident_message, comment_incident_phase

    ports = get_ports()
    ticket_ref = payload["ticket_ref"]
    env = str(payload.get("env") or "")
    decision = IncidentDecision.model_validate(payload["decision"])
    note = decision.resolution_note or decision.rationale or "Resolved via auto_infra"
    actions_ran = payload.get("actions_ran") or []
    prompt = ports.prompts.get(prompt_key="incident.resolution_note")
    variables = {
        "system": prompt.get("system") or "",
        "user": _render(
            str(prompt.get("user") or ""),
            {
                "decision": decision.decision,
                "actions": json.dumps(actions_ran),
                "resolution_note": note,
            },
        ),
        "resolution_note": note,
        "rationale": decision.rationale,
    }
    text = ports.llm.complete(prompt_key="incident.resolution_note", variables=variables)
    msg = build_incident_message(
        status="AUTO_INFRA",
        tracking_id=str(payload.get("tracking_id") or payload.get("incident_ref") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=ticket_ref,
        ticket_url=payload.get("ticket_url"),
        env=env,
        reason=str(text)[:800],
        decision=decision.decision,
        run_ref=str(payload.get("run_ref") or ""),
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        done_by="IT-Support-agent",
    )
    comment_incident_phase(
        ports,
        msg=msg,
        phase="RESOLUTION",
        extras=[
            f"actions_ran={', '.join(actions_ran) if isinstance(actions_ran, list) else actions_ran}",
            f"note={text}",
        ],
    )
    return {"note": text}


@activity.defn
async def close_incident_ticket(payload: dict[str, Any]) -> dict[str, str]:
    """Close ticket + phase comment. Cliq/mail posted by workflow notify activities."""
    from platform_worker.notify_incident import (
        build_incident_message,
        comment_incident_phase,
        soft_ticket_comment,
    )

    ports = get_ports()
    ticket_ref = payload["ticket_ref"]
    run_ref = payload.get("run_ref") or ""
    channel_ref = payload.get("channel_ref") or "cliq:lab"
    env = str(payload.get("env") or "")
    closer = str(payload.get("closer") or "closed")
    decision = str(payload.get("decision") or closer)
    note = str(
        payload.get("note")
        or "Incident run closed. Grafana alert may still fire until resolved/silenced."
    )
    verify_reason = str(payload.get("verify_reason") or note)
    success_summary = str(payload.get("success_summary") or verify_reason)
    verify_evidence = payload.get("verify_evidence") or []

    msg = build_incident_message(
        status="RESOLVED",
        tracking_id=str(payload.get("tracking_id") or ""),
        alert=payload.get("alert") or {},
        ticket_ref=ticket_ref,
        ticket_url=payload.get("ticket_url"),
        env=env,
        reason=verify_reason,
        success_summary=success_summary,
        decision=decision,
        run_ref=run_ref,
        workflow_id=str(payload.get("workflow_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        responsible=str(payload.get("assignee_name") or ""),
        backup=str(payload.get("backup_name") or ""),
        assignee_email=str(payload.get("assignee_email") or ""),
        backup_email=str(payload.get("backup_email") or ""),
        evidence_url=str(payload.get("evidence_url") or ""),
        done_by="IT-Support-agent",
        ended=True,
    )
    comment_incident_phase(
        ports,
        msg=msg,
        phase="CLOSE",
        extras=[
            f"closer={closer}",
            f"note={note}",
            f"Verify evidence: {json.dumps(verify_evidence, default=str)[:2500]}"
            if verify_evidence
            else "",
        ],
    )
    try:
        ports.tickets.update_status(ticket_ref=ticket_ref, status="closed")
        status = "closed"
    except Exception as exc:  # noqa: BLE001
        status = f"close_failed:{exc}"[:200]
        soft_ticket_comment(
            ports,
            ticket_ref=ticket_ref,
            body=f"Could not set ticket status closed: {status}",
        )

    return {"ticket_status": status, "closer": closer, "channel_ref": str(channel_ref)}
