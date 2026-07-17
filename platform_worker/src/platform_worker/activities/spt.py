"""SPT activities — ports only; no service names in this module."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from temporalio import activity

from am_platform_ports.schemas.enums import ErrorClass, FailureMode, RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from am_platform_ports.schemas.spt import ChildRunResult, SptDemandRequest, SptRunSummary, SptSelector
from platform_worker.di import get_ports


def _selector_hash(selector: SptSelector) -> str:
    raw = json.dumps(selector.model_dump(), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@activity.defn
async def create_spt_run(payload: dict[str, Any]) -> dict[str, str]:
    ports = get_ports()
    demand = SptDemandRequest.model_validate(payload["demand"])
    existing = payload.get("run_ref")
    if existing:
        run = ports.runs.get_run(run_ref=str(existing))
        if run is None:
            raise KeyError(f"unknown run_ref: {existing}")
        return {"run_ref": run.run_ref, "demand_ref": demand.demand_ref}
    run = ports.runs.create_run(
        CreateRunRequest(
            kind=RunKind.SPT,
            status=RunStatus.ACCEPTED,
            demand_ref=demand.demand_ref,
            workflow_id=payload.get("workflow_id"),
            requested_selector_hash=_selector_hash(demand.selector),
        )
    )
    return {"run_ref": run.run_ref, "demand_ref": demand.demand_ref}


@activity.defn
async def resolve_spt_targets(payload: dict[str, Any]) -> dict[str, Any]:
    ports = get_ports()
    demand = SptDemandRequest.model_validate(payload["demand"])
    run_ref = payload["run_ref"]
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:resolve",
            run_ref=run_ref,
            name="spt.resolve",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    ids = ports.spt_resolver.resolve(selector=demand.selector)
    allowed: list[str] = []
    skipped: list[str] = []
    for tid in ids:
        if ports.spt_policy.allow(target_ref=tid, request=demand):
            allowed.append(tid)
        else:
            skipped.append(tid)
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run_ref}:resolve",
            run_ref=run_ref,
            name="spt.resolve",
            status=StepStatus.PASSED,
            result_ref=f"count={len(allowed)}",
        )
    )
    max_parallel = int(os.getenv("SPT_MAX_PARALLEL", "5"))
    return {
        "targets": allowed,
        "skipped": skipped,
        "selector_hash": _selector_hash(demand.selector),
        "expanded_count": len(ids),
        "max_parallel": max_parallel,
    }


@activity.defn
async def ensure_spt_preps(payload: dict[str, Any]) -> dict[str, str]:
    """Dedupe prep_ref → dataset_ref for this parent run."""
    ports = get_ports()
    run_ref = payload["run_ref"]
    mapping: dict[str, str] = {}
    seen_prep: dict[str, str] = {}
    for tid in payload["targets"]:
        entry = ports.spt_catalog.get(target_id=tid) or {}
        prep = entry.get("prep_ref")
        if not prep:
            continue
        if prep in seen_prep:
            mapping[tid] = seen_prep[prep]
            continue
        dataset_ref = ports.spt_prep.ensure_dataset(prep_ref=str(prep), parent_run_ref=run_ref)
        seen_prep[str(prep)] = dataset_ref
        mapping[tid] = dataset_ref
    return mapping


@activity.defn
async def run_spt_child(payload: dict[str, Any]) -> dict[str, Any]:
    ports = get_ports()
    parent = payload["parent_run_ref"]
    target_ref = payload["target_ref"]
    dataset_ref = payload.get("dataset_ref")
    child = ports.runs.create_run(
        CreateRunRequest(
            kind=RunKind.SPT,
            status=RunStatus.RUNNING,
            parent_run_ref=parent,
            demand_ref=payload.get("demand_ref"),
            workflow_id=payload.get("workflow_id"),
        )
    )
    step_ref = f"{child.run_ref}:load"
    ports.runs.upsert_step(
        UpsertStepRequest(
            step_ref=step_ref,
            run_ref=child.run_ref,
            name="spt.load",
            status=StepStatus.RUNNING,
            bump_attempts=True,
        )
    )
    entry = ports.spt_catalog.get(target_id=target_ref) or {}
    t0 = time.perf_counter()
    try:
        load_ref = ports.spt_runner.run(
            scenario_ref=str(entry.get("scenario_ref") or "scenario.default"),
            base_url_secret_ref=str(entry.get("base_url_secret_ref") or ""),
            dataset_ref=dataset_ref,
            target_ref=target_ref,
        )
        # observe
        qref = entry.get("query_ref")
        observe_ref = None
        if qref:
            obs = ports.observe.query(query_ref=str(qref), variables={"target_ref": target_ref})
            observe_ref = f"obs:{qref}:{obs.get('pass')}"
        duration_ms = int((time.perf_counter() - t0) * 1000)
        ports.runs.complete_step(step_ref=step_ref, status=StepStatus.PASSED.value, result_ref=load_ref)
        ports.runs.update_run_status(
            run_ref=child.run_ref,
            status=RunStatus.PASSED,
            summary={"target_ref": target_ref, "load_run_ref": load_ref},
        )
        return ChildRunResult(
            target_ref=target_ref,
            status="succeeded",
            load_run_ref=load_ref,
            observe_ref=observe_ref,
            duration_ms=duration_ms,
        ).model_dump()
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        ports.runs.complete_step(
            step_ref=step_ref,
            status=StepStatus.FAILED.value,
            error_class=ErrorClass.FATAL.value,
            result_ref=str(exc)[:200],
        )
        ports.runs.update_run_status(
            run_ref=child.run_ref,
            status=RunStatus.FAILED,
            summary={"target_ref": target_ref, "error": str(exc)[:200]},
        )
        return ChildRunResult(
            target_ref=target_ref,
            status="failed",
            error_class=ErrorClass.FATAL,
            duration_ms=duration_ms,
        ).model_dump()


@activity.defn
async def finalize_spt_run(payload: dict[str, Any]) -> dict[str, Any]:
    ports = get_ports()
    run_ref = payload["run_ref"]
    children = [ChildRunResult.model_validate(c) for c in payload.get("children") or []]
    skipped = [ChildRunResult(target_ref=t, status="skipped") for t in payload.get("skipped") or []]
    cancelled = [ChildRunResult(target_ref=t, status="cancelled") for t in payload.get("cancelled") or []]
    all_children = children + skipped + cancelled
    succeeded = sum(1 for c in all_children if c.status == "succeeded")
    failed = sum(1 for c in all_children if c.status == "failed")
    skipped_n = sum(1 for c in all_children if c.status == "skipped")
    cancelled_n = sum(1 for c in all_children if c.status == "cancelled")
    if failed == 0 and succeeded >= 1:
        overall = "succeeded"
        run_status = RunStatus.PASSED
    elif succeeded >= 1 and failed >= 1:
        overall = "partial"
        run_status = RunStatus.PARTIAL
    elif succeeded == 0 and failed >= 1:
        overall = "failed"
        run_status = RunStatus.FAILED
    else:
        overall = "failed"
        run_status = RunStatus.FAILED

    summary = SptRunSummary(
        run_id=run_ref,
        requested_count=int(payload.get("requested_count") or len(all_children)),
        ran_count=succeeded + failed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped_n,
        cancelled=cancelled_n,
        children=all_children,
        overall_status=overall,
    )
    try:
        doc = ports.docs.put(
            key=f"spt/{run_ref}/summary.json",
            content=summary.model_dump_json().encode("utf-8"),
            content_type="application/json",
        )
        summary.docs_ref = doc.docs_ref
    except Exception:
        pass

    ports.runs.update_run_status(
        run_ref=run_ref,
        status=run_status,
        summary=summary.model_dump(),
    )

    # Notify with counts — never false all-green on partial
    from am_platform_ports.schemas.core import NotifyCard

    title = f"spt.completed {overall}"
    body = (
        f"succeeded={succeeded} failed={failed} skipped={skipped_n} cancelled={cancelled_n} "
        f"ran={summary.ran_count}/{summary.requested_count}"
    )
    try:
        ports.notifier.send_card(
            channel_ref="cliq:lab",
            card=NotifyCard(
                event="spt.completed",
                title=title,
                body=body,
                refs={
                    "run_ref": run_ref,
                    "docs_ref": summary.docs_ref or "",
                    "overall_status": overall,
                },
            ),
        )
    except Exception:
        pass

    return summary.model_dump()
