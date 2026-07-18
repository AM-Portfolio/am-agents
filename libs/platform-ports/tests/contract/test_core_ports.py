"""Contract tests for FakeRunStore + core fakes."""

from datetime import UTC, datetime, timedelta

import pytest

from am_platform_ports.fakes import FakeDocStore, FakeRunStore, FakeTicketStore
from am_platform_ports.ports.docs import DocStore
from am_platform_ports.ports.run import RunStore
from am_platform_ports.ports.ticket import TicketStore
from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from am_platform_ports.schemas.spt import SptDemandRequest, SptSelector


def test_ticket_store_protocol() -> None:
    store: TicketStore = FakeTicketStore()
    ref = store.create(title="t", description="d", priority="P1")
    store.assign(ticket_ref=ref.ticket_ref, assignee_ref="user:1")
    store.comment(ticket_ref=ref.ticket_ref, body="hi")
    store.update_status(ticket_ref=ref.ticket_ref, status="done")
    assert ref.ticket_ref.startswith("ticket-")


def test_doc_store_protocol() -> None:
    store: DocStore = FakeDocStore()
    ref = store.put(key="a/b.txt", content=b"x")
    assert store.exists(docs_ref=ref.docs_ref)
    assert store.get(docs_ref=ref.docs_ref) == b"x"


def test_runstore_intake_and_steps() -> None:
    rs: RunStore = FakeRunStore()
    run = rs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, incident_ref="inc-1", workflow_id="wf-1")
    )
    assert run.status == RunStatus.ACCEPTED

    step = rs.upsert_step(
        UpsertStepRequest(
            step_ref="step-triage",
            run_ref=run.run_ref,
            name="triage",
            status=StepStatus.RUNNING,
        )
    )
    assert step.status == StepStatus.RUNNING
    assert rs.get_run(run_ref=run.run_ref).status == RunStatus.RUNNING

    rs.complete_step(step_ref="step-triage", status="passed")
    assert rs.list_steps(run_ref=run.run_ref)[0].status == StepStatus.PASSED


def test_runstore_claim_pending() -> None:
    rs = FakeRunStore()
    run = rs.create_run(CreateRunRequest(kind=RunKind.VERIFY))
    rs.upsert_step(
        UpsertStepRequest(
            step_ref="step-metrics",
            run_ref=run.run_ref,
            name="metrics",
            status=StepStatus.PENDING,
        )
    )
    lease = datetime.now(UTC) + timedelta(minutes=5)
    claimed = rs.claim_pending(worker_id="w1", lease_until=lease, limit=1)
    assert len(claimed) == 1
    assert claimed[0].status == StepStatus.CLAIMED
    assert claimed[0].worker_id == "w1"

    again = rs.claim_pending(worker_id="w2", lease_until=lease, limit=1)
    assert again == []


def test_spt_empty_selector_fatal() -> None:
    with pytest.raises(ValueError, match="empty selector"):
        SptDemandRequest(demand_ref="d1", selector=SptSelector())


def test_spt_selector_with_ids() -> None:
    req = SptDemandRequest(demand_ref="d1", selector=SptSelector(ids=["svc-a", "svc-b"]))
    assert req.selector.ids == ["svc-a", "svc-b"]
