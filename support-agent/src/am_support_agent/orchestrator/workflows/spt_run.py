"""SptRun workflow scaffold on queue support-agent-v2.

Temporal type name matches legacy (`SptRunWorkflow`). Catalog resolve is
read-only; fan-out side effects remain gated.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from am_support_agent.orchestrator.activities.spt import (
        bootstrap_spt,
        resolve_spt_catalog,
    )


@workflow.defn(name="SptRunWorkflow")
class SptRunWorkflow:
    def __init__(self) -> None:
        self._status: str = "init"
        self._run_ref: str | None = None

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "run_ref": self._run_ref,
            "status": self._status,
            "module": "support-agent",
        }

    @workflow.run
    async def run(self, input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(input or {})
        demand = dict(payload.get("demand") or payload)
        self._run_ref = str(
            payload.get("run_ref")
            or demand.get("demand_ref")
            or workflow.info().workflow_id
        )
        self._status = "resolving_catalog"
        catalog = await workflow.execute_activity(
            resolve_spt_catalog,
            {"demand": demand, "demand_ref": self._run_ref},
            start_to_close_timeout=timedelta(seconds=60),
        )
        self._status = "bootstrap"
        boot = await workflow.execute_activity(
            bootstrap_spt,
            {"demand": demand, "run_ref": self._run_ref},
            start_to_close_timeout=timedelta(seconds=60),
        )
        if boot.get("gated"):
            self._status = "gated"
            return {
                "status": "gated",
                "run_ref": self._run_ref,
                "catalog": catalog,
                "bootstrap": boot,
            }
        self._status = "completed"
        return {
            "status": "completed",
            "run_ref": self._run_ref,
            "catalog": catalog,
            "bootstrap": boot,
        }
