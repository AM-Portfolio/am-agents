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
    ports = get_ports()
    run_ref = payload["run_ref"]
    alert = ports.redactor.scrub(payload=payload.get("alert") or {})
    if not isinstance(alert, dict):
        alert = {}

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
    decision = enforce_decision(_parse_decision_json(raw))

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:analyze",
            run_ref=run_ref,
            name="incident.analyze",
            status=StepStatus.PASSED,
            result_ref=decision.decision,
        )
    )
    return decision.model_dump()


@activity.defn
async def apply_ticket_decision(payload: dict[str, Any]) -> dict[str, str]:
    """Comment decision onto ticket + optional Cliq escalate for needs_human."""
    ports = get_ports()
    run_ref = payload["run_ref"]
    ticket_ref = payload["ticket_ref"]
    decision = IncidentDecision.model_validate(payload["decision"])
    channel_ref = payload.get("channel_ref") or "cliq:lab"

    body = decision.ticket_update or decision.rationale or decision.decision
    ports.tickets.comment(ticket_ref=ticket_ref, body=f"[agent:{decision.decision}] {body}")

    if decision.decision == "needs_human":
        from am_platform_ports.schemas.core import NotifyCard

        ports.notifier.send_card(
            channel_ref=channel_ref,
            card=NotifyCard(
                event="needs_human",
                title="Needs human (code/service)",
                body=decision.rationale or body,
                refs={"ticket_ref": ticket_ref, "run_ref": run_ref},
            ),
        )
        ports.runs.update_run_status(
            run_ref=run_ref,
            status=RunStatus.NEEDS_HUMAN,
            summary={"decision": decision.decision, "ticket_ref": ticket_ref},
        )
    elif decision.decision == "ignore":
        ports.runs.update_run_status(
            run_ref=run_ref,
            status=RunStatus.CANCELLED,
            summary={"decision": "ignore", "rationale": decision.rationale, "ticket_ref": ticket_ref},
        )
    return {"ok": "1"}


@activity.defn
async def handoff_infra_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """Handoff to kagent_infra then run allowlisted actions one-by-one; never raise on tool fail."""
    ports = get_ports()
    run_ref = payload["run_ref"]
    decision = IncidentDecision.model_validate(payload["decision"])
    attempts: list[dict[str, Any]] = []
    actions_ran: list[str] = []
    handoff_ref: str | None = None

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:handoff",
            run_ref=run_ref,
            name="incident.handoff",
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
        attempts.append({"step": "handoff", "status": "ok", "handoff_ref": handoff_ref})
    except Exception as exc:  # noqa: BLE001 — capture for human handoff
        reason = f"handoff failed: {exc}"[:400]
        attempts.append({"step": "handoff", "status": "failed", "error": reason})
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=f"{run_ref}:handoff",
                run_ref=run_ref,
                name="incident.handoff",
                status=StepStatus.FAILED,
                result_ref="handoff_failed",
            )
        )
        return {
            "ok": False,
            "handoff_ref": None,
            "actions_ran": [],
            "attempts": attempts,
            "failure_reason": reason,
            "summary": reason,
        }

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:handoff",
            run_ref=run_ref,
            name="incident.handoff",
            status=StepStatus.PASSED,
            result_ref=handoff_ref,
        )
    )

    for action in decision.proposed_actions:
        try:
            plan = ports.infra.plan(
                incident_ref=payload.get("incident_ref") or "",
                context={
                    "ticket_ref": payload.get("ticket_ref"),
                    "proposed_actions": [action.model_dump()],
                    "alert": payload.get("alert") or {},
                },
            )
            done = ports.infra.execute(plan=plan)
            actions_ran.extend(done.actions_ran)
            attempts.append(
                {
                    "step": "tool",
                    "tool_name": action.tool_name,
                    "status": "ok",
                    "work_ref": done.work_ref,
                }
            )
        except Exception as exc:  # noqa: BLE001
            reason = f"tool {action.tool_name} failed: {exc}"[:400]
            attempts.append(
                {
                    "step": "tool",
                    "tool_name": action.tool_name,
                    "status": "failed",
                    "error": reason,
                }
            )
            ports.runs.upsert_step(
                UpsertStepRequest(
                    step_ref=f"{run_ref}:infra.execute",
                    run_ref=run_ref,
                    name="infra.execute",
                    status=StepStatus.FAILED,
                    result_ref=action.tool_name,
                )
            )
            return {
                "ok": False,
                "handoff_ref": handoff_ref,
                "actions_ran": actions_ran,
                "attempts": attempts,
                "failure_reason": reason,
                "summary": reason,
            }

    summary = ports.redactor.scrub(
        payload={"summary": f"work_done actions={','.join(actions_ran)}", "actions": actions_ran}
    )
    return {
        "ok": True,
        "handoff_ref": handoff_ref,
        "actions_ran": actions_ran,
        "attempts": attempts,
        "failure_reason": None,
        "summary": summary.get("summary") if isinstance(summary, dict) else str(summary),
    }


@activity.defn
async def escalate_unsolved(payload: dict[str, Any]) -> dict[str, str]:
    """Document attempts + why unsolved; ticket + Cliq + RunStore → needs_human."""
    from am_platform_ports.schemas.core import NotifyCard

    ports = get_ports()
    run_ref = payload["run_ref"]
    ticket_ref = payload["ticket_ref"]
    channel_ref = payload.get("channel_ref") or "cliq:lab"
    decision = IncidentDecision.model_validate(payload.get("decision") or {"decision": "auto_infra"})
    attempts = payload.get("attempts") or []
    failure_reason = str(payload.get("failure_reason") or "unknown")
    verify_status = str(payload.get("verify_status") or "")
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

    body = (
        f"[agent:unsolved→human]\n"
        f"Accepted as: {decision.decision}\n"
        f"Why accepted: {decision.rationale}\n"
        f"What was tried: {json.dumps(attempts, default=str)}\n"
        f"Why not solved: {failure_reason}\n"
        f"Verify: {verify_status or 'n/a'}\n"
        f"Handoff note:\n{note}"
    )
    ports.tickets.comment(ticket_ref=ticket_ref, body=body)
    ports.notifier.send_card(
        channel_ref=channel_ref,
        card=NotifyCard(
            event="needs_human",
            title="Agent could not solve — needs developer",
            body=f"{failure_reason}\n{note}"[:1500],
            refs={"ticket_ref": ticket_ref, "run_ref": run_ref},
        ),
    )
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
    ports = get_ports()
    ticket_ref = payload["ticket_ref"]
    decision = IncidentDecision.model_validate(payload["decision"])
    note = decision.resolution_note or decision.rationale or "Resolved via auto_infra"
    prompt = ports.prompts.get(prompt_key="incident.resolution_note")
    variables = {
        "system": prompt.get("system") or "",
        "user": _render(
            str(prompt.get("user") or ""),
            {
                "decision": decision.decision,
                "actions": json.dumps(payload.get("actions_ran") or []),
                "resolution_note": note,
            },
        ),
        "resolution_note": note,
        "rationale": decision.rationale,
    }
    text = ports.llm.complete(prompt_key="incident.resolution_note", variables=variables)
    ports.tickets.comment(ticket_ref=ticket_ref, body=f"[resolution] {text}")
    return {"note": text}
