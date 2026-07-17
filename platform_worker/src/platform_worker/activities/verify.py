"""Verify run activities — Gate A claim loop (ADR-005)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity

from am_platform_ports.schemas.enums import ErrorClass, RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from platform_worker.catalog_verify import load_verify_checks
from platform_worker.di import get_ports


@activity.defn
async def spawn_verify_run(payload: dict[str, Any]) -> dict[str, str]:
    """Create kind=verify run + pending steps from catalog."""
    ports = get_ports()
    parent = payload["parent_run_ref"]
    verify = ports.runs.create_run(
        CreateRunRequest(
            kind=RunKind.VERIFY,
            status=RunStatus.ACCEPTED,
            parent_run_ref=parent,
            incident_ref=payload.get("incident_ref"),
            ticket_ref=payload.get("ticket_ref"),
            workflow_id=payload.get("workflow_id"),
        )
    )
    for check in load_verify_checks():
        check_ref = str(check["check_ref"])
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=f"{verify.run_ref}:{check_ref}",
                run_ref=verify.run_ref,
                name=check_ref,
                check_ref=check_ref,
                status=StepStatus.PENDING,
            )
        )
    ports.runs.update_run_status(
        run_ref=parent,
        status=RunStatus.RUNNING,
        summary={
            "ticket_ref": payload.get("ticket_ref"),
            "verify_run_ref": verify.run_ref,
            "gate": "awaiting_verify",
        },
    )
    return {"verify_run_ref": verify.run_ref}


@activity.defn
async def claim_and_execute_verify(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Claim pending verify steps (SKIP LOCKED), execute via ObservabilityPort, complete.
    Returns aggregate status: passed | failed | partial.
    """
    ports = get_ports()
    verify_run_ref = payload["verify_run_ref"]
    worker_id = payload.get("worker_id") or "verify-worker"

    lease = datetime.now(UTC) + timedelta(minutes=5)
    for check in load_verify_checks():
        check_ref = str(check["check_ref"])
        claimed = ports.runs.claim_pending(
            worker_id=worker_id,
            lease_until=lease,
            limit=5,
            name=check_ref,
        )
        claimed = [s for s in claimed if s.run_ref == verify_run_ref]
        for step in claimed:
            query_ref = str(check.get("query_ref") or check_ref)
            ports.runs.upsert_step(
                UpsertStepRequest(
                    step_ref=step.step_ref,
                    run_ref=step.run_ref,
                    name=step.name,
                    check_ref=step.check_ref,
                    status=StepStatus.RUNNING,
                    worker_id=worker_id,
                )
            )
            try:
                alert = payload.get("alert") or {}
                labels = dict(alert.get("labels") or {})
                env = (
                    payload.get("env")
                    or labels.get("env")
                    or alert.get("env")
                    or ""
                )
                result = ports.observe.query(
                    query_ref=query_ref,
                    variables={
                        "incident_ref": payload.get("incident_ref"),
                        "env": env,
                        "labels": labels,
                        "namespace": labels.get("namespace") or "",
                        "service": labels.get("service") or labels.get("application") or "",
                        "deployment": labels.get("deployment") or labels.get("service") or "",
                        "pod": labels.get("pod") or "",
                        "alertname": labels.get("alertname") or "",
                        "value_string": alert.get("value_string") or "",
                    },
                )
                # Fail closed: missing/false pass must not close the incident
                ok = result.get("pass") is True
                if result.get("error"):
                    ok = False
                result_ref = None
                try:
                    doc = ports.docs.put(
                        key=f"verify/{verify_run_ref}/{step.name}.json",
                        content=json.dumps(result, default=str).encode("utf-8"),
                        content_type="application/json",
                    )
                    result_ref = doc.docs_ref
                except Exception:
                    result_ref = f"inline:{json.dumps(result, default=str)[:200]}"
                ports.runs.complete_step(
                    step_ref=step.step_ref,
                    status=StepStatus.PASSED.value if ok else StepStatus.FAILED.value,
                    result_ref=result_ref,
                    error_class=None if ok else ErrorClass.FATAL.value,
                )
            except Exception as exc:
                ports.runs.complete_step(
                    step_ref=step.step_ref,
                    status=StepStatus.FAILED.value,
                    error_class=ErrorClass.RETRYABLE.value,
                    result_ref=str(exc)[:200],
                )

    steps = ports.runs.list_steps(run_ref=verify_run_ref)
    passed = sum(1 for s in steps if s.status == StepStatus.PASSED)
    failed = sum(1 for s in steps if s.status == StepStatus.FAILED)
    pending = sum(
        1 for s in steps if s.status in {StepStatus.PENDING, StepStatus.CLAIMED, StepStatus.RUNNING}
    )
    if pending:
        status = RunStatus.RUNNING
    elif failed == 0 and passed > 0:
        status = RunStatus.PASSED
    elif passed == 0 and failed > 0:
        status = RunStatus.FAILED
    else:
        status = RunStatus.PARTIAL

    ports.runs.update_run_status(
        run_ref=verify_run_ref,
        status=status,
        summary={"passed": passed, "failed": failed, "pending": pending},
    )
    return {
        "verify_run_ref": verify_run_ref,
        "status": status.value,
        "passed": passed,
        "failed": failed,
        "pending": pending,
    }
