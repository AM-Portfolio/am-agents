"""SptRunWorkflow — resolve → prep → fan-out children → aggregate (ADR-004)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_worker.activities import spt as sacts


@dataclass
class SptRunInput:
    demand: dict[str, Any]
    run_ref: str | None = None


@workflow.defn(name="SptRunWorkflow")
class SptRunWorkflow:
    def __init__(self) -> None:
        self._run_ref: str | None = None
        self._status: str | None = None

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {"run_ref": self._run_ref, "status": self._status}

    @workflow.run
    async def run(self, input: SptRunInput | dict[str, Any]) -> dict[str, Any]:
        if isinstance(input, dict):
            demand = dict(input.get("demand") or input)
            pre_run_ref = input.get("run_ref")
        else:
            demand = input.demand
            pre_run_ref = input.run_ref

        retry = RetryPolicy(maximum_attempts=2)
        short = timedelta(seconds=120)
        child_timeout = timedelta(minutes=5)

        created = await workflow.execute_activity(
            sacts.create_spt_run,
            {
                "demand": demand,
                "workflow_id": workflow.info().workflow_id,
                "run_ref": pre_run_ref,
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._run_ref = created["run_ref"]
        self._status = "resolving"

        resolved = await workflow.execute_activity(
            sacts.resolve_spt_targets,
            {"demand": demand, "run_ref": self._run_ref},
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        targets: list[str] = list(resolved["targets"])
        skipped: list[str] = list(resolved.get("skipped") or [])
        max_parallel = int(resolved.get("max_parallel") or 5)
        requested = int(demand.get("parallelism") or 2)
        parallelism = max(1, min(requested, max_parallel))
        failure_mode = str(demand.get("failure_mode") or "continue")

        prep_map = await workflow.execute_activity(
            sacts.ensure_spt_preps,
            {"run_ref": self._run_ref, "targets": targets},
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._status = "running"

        children: list[dict[str, Any]] = []
        cancelled: list[str] = []
        fail_fast_triggered = False

        for i in range(0, len(targets), max(1, parallelism)):
            if fail_fast_triggered:
                cancelled.extend(targets[i:])
                break
            batch = targets[i : i + parallelism]
            batch_results = await asyncio.gather(
                *[
                    workflow.execute_activity(
                        sacts.run_spt_child,
                        {
                            "parent_run_ref": self._run_ref,
                            "target_ref": tid,
                            "dataset_ref": prep_map.get(tid),
                            "demand_ref": demand.get("demand_ref"),
                            "workflow_id": workflow.info().workflow_id,
                        },
                        start_to_close_timeout=child_timeout,
                        retry_policy=retry,
                    )
                    for tid in batch
                ]
            )
            for res in batch_results:
                children.append(res)
                if failure_mode == "fail_fast" and res.get("status") == "failed":
                    fail_fast_triggered = True

        summary = await workflow.execute_activity(
            sacts.finalize_spt_run,
            {
                "run_ref": self._run_ref,
                "children": children,
                "skipped": skipped,
                "cancelled": cancelled,
                "requested_count": len(targets) + len(skipped),
            },
            start_to_close_timeout=short,
            retry_policy=retry,
        )
        self._status = summary.get("overall_status")
        return summary
