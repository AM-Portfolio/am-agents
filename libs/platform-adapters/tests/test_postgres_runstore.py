"""Postgres RunStore unit tests — require RUN_STORE_DSN (skipped otherwise)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_STORE_DSN"),
    reason="RUN_STORE_DSN not set",
)


def test_postgres_runstore_intake_steps_claim() -> None:
    from am_platform_adapters.providers.postgres_runstore import PostgresRunStore

    rs = PostgresRunStore()
    run = rs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="inc-pg-test", workflow_id="wf-1")
    )
    assert run.status == RunStatus.ACCEPTED
    assert rs.get_run(run_ref=run.run_ref) is not None

    step = rs.upsert_step(
        UpsertStepRequest(
            step_ref=f"{run.run_ref}:verify",
            run_ref=run.run_ref,
            name="verify.metrics",
            status=StepStatus.PENDING,
            check_ref="verify.metrics.error_rate",
        )
    )
    assert step.status == StepStatus.PENDING
    assert rs.get_run(run_ref=run.run_ref).status == RunStatus.RUNNING

    lease = datetime.now(UTC) + timedelta(minutes=5)
    claimed = rs.claim_pending(worker_id="w1", lease_until=lease, limit=1, name="verify.metrics")
    assert len(claimed) == 1
    assert claimed[0].status == StepStatus.CLAIMED
    assert claimed[0].worker_id == "w1"

    done = rs.complete_step(step_ref=claimed[0].step_ref, status="passed", result_ref="ok")
    assert done.status == StepStatus.PASSED

    rs.update_run_status(run_ref=run.run_ref, status=RunStatus.PASSED, summary={"ok": True})
    assert rs.get_run(run_ref=run.run_ref).status == RunStatus.PASSED
