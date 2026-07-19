from am_support_agent.observability.agent_work import (
    build_event,
    map_domain_status,
)
from am_support_agent.observability.agent_work import WorkOutcome, WorkStatus
from am_support_agent.stores.telemetry_outbox import MemoryTelemetryOutbox


def test_domain_status_mapping():
    assert map_domain_status("human_required") == (
        WorkStatus.NEEDS_HUMAN,
        WorkOutcome.HUMAN_HANDOFF,
    )


def test_outbox_idempotent():
    box = MemoryTelemetryOutbox()
    a = build_event(
        event_name="agent.work.started",
        workflow_id="alert-incident-t1",
        run_ref="run-1",
        sequence=1,
    )
    b = build_event(
        event_name="agent.work.started",
        workflow_id="alert-incident-t1",
        run_ref="run-1",
        sequence=1,
    )
    r1 = box.append(a)
    r2 = box.append(b)
    assert r1.dedupe_key == r2.dedupe_key
    assert box.pending_count() == 1
    claimed = box.claim_batch()
    assert len(claimed) == 1
    box.mark_delivered(claimed[0].event_id)
    assert box.pending_count() == 0
