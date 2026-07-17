"""Verify run activities — Gate A claim loop (ADR-005)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity

from am_platform_ports.schemas.enums import ErrorClass, RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from platform_worker.catalog_verify import load_verify_checks
from platform_worker.di import get_ports

logger = logging.getLogger(__name__)

# Safe keys allowed on evidence metadata (no secrets / full payloads)
_SAFE_META_KEYS = (
    "redis_version",
    "uptime_in_seconds",
    "promql",
    "variables",
)


def _evidence_from_result(
    *,
    check_ref: str,
    query_ref: str,
    result: dict[str, Any],
    result_ref: str | None,
    ok: bool,
    catalog_pass_when: str | None = None,
) -> dict[str, Any]:
    """Build a serializable per-check evidence record for Temporal / logs / E2E."""
    source = str(result.get("source") or "unknown")
    reason = result.get("reason")
    if not reason:
        if result.get("error"):
            reason = f"{check_ref} failed via {source}: {result['error']}"
        elif ok:
            reason = (
                f"{check_ref} passed via {source}: "
                f"value={result.get('value')} pass_when="
                f"{result.get('pass_when') or catalog_pass_when}"
            )
        else:
            reason = (
                f"{check_ref} failed via {source}: "
                f"value={result.get('value')} does not satisfy "
                f"{result.get('pass_when') or catalog_pass_when or 'pass criteria'}"
            )
    evidence: dict[str, Any] = {
        "check_ref": check_ref,
        "query_ref": query_ref,
        "passed": ok,
        "status": "passed" if ok else "failed",
        "source": source,
        "reason": str(reason),
        "value": result.get("value"),
        "threshold": result.get("threshold"),
        "pass_when": result.get("pass_when") or catalog_pass_when,
        "request_id": result.get("request_id"),
        "error": result.get("error"),
        "result_ref": result_ref,
    }
    meta: dict[str, Any] = {}
    for key in _SAFE_META_KEYS:
        if result.get(key) is not None:
            meta[key] = result[key]
    if meta:
        evidence["metadata"] = meta
    return evidence


def _aggregate_reason(evidence: list[dict[str, Any]], status: str) -> str:
    if not evidence:
        return f"verify {status}: no checks executed"
    parts = [
        f"{e.get('check_ref')}={'PASS' if e.get('passed') else 'FAIL'}: {e.get('reason')}"
        for e in evidence
    ]
    return f"verify {status}: " + "; ".join(parts)


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
    Returns aggregate status plus per-check evidence (reasons for pass/fail).
    """
    ports = get_ports()
    verify_run_ref = payload["verify_run_ref"]
    worker_id = payload.get("worker_id") or "verify-worker"
    evidence: list[dict[str, Any]] = []

    lease = datetime.now(UTC) + timedelta(minutes=5)
    for check in load_verify_checks():
        check_ref = str(check["check_ref"])
        catalog_pass_when = str(check.get("pass_when") or "") or None
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
                ev = _evidence_from_result(
                    check_ref=check_ref,
                    query_ref=query_ref,
                    result=result if isinstance(result, dict) else {},
                    result_ref=result_ref,
                    ok=ok,
                    catalog_pass_when=catalog_pass_when,
                )
                evidence.append(ev)
                logger.info(
                    "verify_check check_ref=%s query_ref=%s passed=%s source=%s "
                    "value=%s pass_when=%s reason=%s request_id=%s result_ref=%s",
                    ev.get("check_ref"),
                    ev.get("query_ref"),
                    ev.get("passed"),
                    ev.get("source"),
                    ev.get("value"),
                    ev.get("pass_when"),
                    ev.get("reason"),
                    ev.get("request_id"),
                    ev.get("result_ref"),
                )
            except Exception as exc:
                err = str(exc)[:200]
                ports.runs.complete_step(
                    step_ref=step.step_ref,
                    status=StepStatus.FAILED.value,
                    error_class=ErrorClass.RETRYABLE.value,
                    result_ref=err,
                )
                ev = {
                    "check_ref": check_ref,
                    "query_ref": query_ref,
                    "passed": False,
                    "status": "failed",
                    "source": "exception",
                    "reason": f"{check_ref} failed with exception: {err}",
                    "value": None,
                    "threshold": None,
                    "pass_when": catalog_pass_when,
                    "request_id": None,
                    "error": err,
                    "result_ref": err,
                }
                evidence.append(ev)
                logger.info(
                    "verify_check check_ref=%s query_ref=%s passed=%s source=%s "
                    "value=%s pass_when=%s reason=%s request_id=%s result_ref=%s",
                    ev["check_ref"],
                    ev["query_ref"],
                    False,
                    "exception",
                    None,
                    catalog_pass_when,
                    ev["reason"],
                    None,
                    err,
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

    verify_reason = _aggregate_reason(evidence, status.value)
    ports.runs.update_run_status(
        run_ref=verify_run_ref,
        status=status,
        summary={
            "passed": passed,
            "failed": failed,
            "pending": pending,
            "verify_reason": verify_reason,
            "evidence_count": len(evidence),
        },
    )
    logger.info(
        "verify_aggregate verify_run_ref=%s status=%s passed=%s failed=%s pending=%s reason=%s",
        verify_run_ref,
        status.value,
        passed,
        failed,
        pending,
        verify_reason,
    )
    return {
        "verify_run_ref": verify_run_ref,
        "status": status.value,
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "evidence": evidence,
        "verify_evidence": evidence,
        "verify_reason": verify_reason,
    }
