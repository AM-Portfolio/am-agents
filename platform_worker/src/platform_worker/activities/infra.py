"""InfraOps activity — plan + allowlisted execute → work_done (before verify)."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from am_platform_ports.schemas.enums import StepStatus
from am_platform_ports.schemas.run import UpsertStepRequest
from platform_worker.di import get_ports


@activity.defn
async def plan_and_execute_fix(payload: dict[str, Any]) -> dict[str, Any]:
    """
    InfraOps plan → execute via ToolSandbox allowlist → work_done milestone.
    ADR-005: verify is spawned only after this returns.
    """
    ports = get_ports()
    run_ref = payload["run_ref"]
    incident_ref = payload.get("incident_ref") or ""
    ticket_ref = payload.get("ticket_ref")

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:infra.plan",
            run_ref=run_ref,
            name="infra.plan",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    plan = ports.infra.plan(
        incident_ref=incident_ref,
        context={"ticket_ref": ticket_ref, "alert": payload.get("alert") or {}},
    )
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:infra.plan",
            run_ref=run_ref,
            name="infra.plan",
            status=StepStatus.PASSED,
            result_ref=plan.plan_ref,
        )
    )

    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:infra.execute",
            run_ref=run_ref,
            name="infra.execute",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    done = ports.infra.execute(plan=plan)
    # Redact before storing summary in ledger
    summary = ports.redactor.scrub(payload={"summary": done.summary, "actions": done.actions_ran})
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:infra.execute",
            run_ref=run_ref,
            name="infra.execute",
            status=StepStatus.PASSED,
            result_ref=done.work_ref,
        )
    )
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:infra.work_done",
            run_ref=run_ref,
            name="infra.work_done",
            status=StepStatus.PASSED,
            result_ref=done.work_ref,
        )
    )
    return {
        "plan_ref": plan.plan_ref,
        "work_ref": done.work_ref,
        "summary": summary.get("summary") if isinstance(summary, dict) else done.summary,
        "actions_ran": done.actions_ran,
    }
