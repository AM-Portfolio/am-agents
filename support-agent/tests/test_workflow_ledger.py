"""Workflow ledger unit tests."""

from __future__ import annotations

from am_support_agent.stores.workflow_ledger import (
    MemoryWorkflowLedger,
    SqliteWorkflowLedger,
    WorkflowKind,
    WorkflowRunStatus,
    WorkflowStepStatus,
)


def test_memory_ledger_create_step_and_handoff():
    ledger = MemoryWorkflowLedger()
    run = ledger.create_run(
        kind=WorkflowKind.ALERT_INCIDENT,
        tracking_id="trk-1",
        workflow_id="alert-incident-trk-1",
    )
    assert run.status == WorkflowRunStatus.ACCEPTED
    step = ledger.upsert_step(
        run_ref=run.run_ref,
        name="validate",
        status=WorkflowStepStatus.PASSED,
        bump_attempts=True,
        result_ref="evidence:1",
    )
    assert step.attempts == 1
    child = ledger.handoff(
        from_run_ref=run.run_ref,
        to_kind=WorkflowKind.HANDOFF,
        context={"agent": "kagent_infra"},
    )
    assert child.parent_run_ref == run.run_ref
    assert ledger.get_by_workflow_id("alert-incident-trk-1") is not None
    assert any(s.name == "handoff" for s in ledger.list_steps(run.run_ref))


def test_sqlite_ledger_roundtrip(tmp_path):
    path = tmp_path / "workflows.db"
    ledger = SqliteWorkflowLedger(str(path))
    run = ledger.create_run(kind=WorkflowKind.SPT, demand_ref="d1", tracking_id="d1")
    ledger.update_run(
        run.run_ref,
        status=WorkflowRunStatus.RUNNING,
        workflow_id="spt-d1",
        summary={"phase": "prep"},
        validation_json={"status": "confirmed"},
    )
    loaded = ledger.get_by_workflow_id("spt-d1")
    assert loaded is not None
    assert loaded.status == WorkflowRunStatus.RUNNING
    assert loaded.summary["phase"] == "prep"
    assert loaded.validation_json == {"status": "confirmed"}
