from agent_common.telemetry import (
    build_event,
    map_domain_status,
    sanitize_attributes,
)
from agent_common.telemetry.vocabulary import WorkOutcome, WorkStatus


def test_map_domain_status():
    assert map_domain_status("human_required") == (
        WorkStatus.NEEDS_HUMAN,
        WorkOutcome.HUMAN_HANDOFF,
    )
    assert map_domain_status("recovered") == (WorkStatus.PASSED, WorkOutcome.RECOVERED)
    assert map_domain_status("gated") == (WorkStatus.CANCELLED, WorkOutcome.GATED)


def test_build_event_dedupe_stable():
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
    assert a.dedupe_key == b.dedupe_key
    assert a.event_id != b.event_id


def test_sanitize_strips_secrets():
    cleaned = sanitize_attributes(
        {"token": "abc", "nested": {"password": "x"}, "ok": "y"}
    )
    assert cleaned["token"] == "***"
    assert cleaned["nested"]["password"] == "***"
    assert cleaned["ok"] == "y"


def test_rejects_unknown_event():
    try:
        build_event(event_name="not.a.real.event")
        assert False, "expected ValueError"
    except ValueError:
        pass
