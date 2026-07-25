"""HITL signal continuity and gated incident/SPT activities."""

from __future__ import annotations

import pytest

from am_support_agent.orchestrator.hitl import (
    HITL_SIGNAL_NAMES,
    SIGNAL_ALERT_REFIRED,
    SIGNAL_ALERT_RESOLVED,
    SIGNAL_APPROVE,
    SIGNAL_APPROVE_INVESTIGATION,
    SIGNAL_APPROVE_KNOWN_FIX,
    SIGNAL_APPROVE_SILENCE,
    SIGNAL_FEEDBACK,
    HitlState,
)


def test_hitl_signal_names_include_purpose_approvals():
    assert SIGNAL_APPROVE == "approve"
    assert SIGNAL_ALERT_RESOLVED == "alert.resolved"
    assert SIGNAL_ALERT_REFIRED == "alert.refired"
    assert SIGNAL_APPROVE_INVESTIGATION == "approve.investigation"
    assert SIGNAL_APPROVE_KNOWN_FIX == "approve.known_fix"
    assert SIGNAL_APPROVE_SILENCE == "approve.silence"
    assert SIGNAL_FEEDBACK == "alert.feedback"
    assert "approve" in HITL_SIGNAL_NAMES
    assert "approve.silence" in HITL_SIGNAL_NAMES


def test_hitl_approval_purposes_are_isolated():
    state = HitlState()
    state.apply_signal(SIGNAL_APPROVE_SILENCE, {"actor": "ops", "request_id": "r1"})
    assert state.silence_approved is True
    assert state.investigation_approved is False
    assert state.known_fix_approved is False
    assert not state.waiting_satisfied()
    assert state.silence_waiting_satisfied()

    state.apply_signal(SIGNAL_APPROVE_INVESTIGATION, {"actor": "ops"})
    assert state.waiting_satisfied()
    assert state.investigation_approved is True


def test_hitl_state_waiting():
    state = HitlState()
    assert not state.waiting_satisfied()
    state.apply_signal(SIGNAL_APPROVE)
    assert state.waiting_satisfied()
    assert state.as_dict()["approved"] is True


@pytest.mark.asyncio
async def test_human_handoff_raises_application_error(monkeypatch):
    """_handoff_to_human must complete all side-effects then raise ApplicationError
    so Temporal marks the workflow run as FAILED (not Completed)."""
    import pytest
    from temporalio.exceptions import ApplicationError

    from am_support_agent.orchestrator.workflows.alert_incident import (
        AlertIncidentWorkflow,
    )

    incident = AlertIncidentWorkflow()
    incident._tracking_id = "AM-HITL-1"
    incident._state = {
        "owner": {"assignee_ref": "user:ops"},
        "work_item": {"id": "INC-1"},
    }
    calls: list[str] = []

    async def ticket_and_notify(actions, *, comment_body=None):
        assert actions == []
        assert "Human action required" in comment_body
        calls.append("ticket_and_notify")

    async def persist(*, outcome, actions=None):
        assert outcome == "human_required"
        assert actions == []
        incident._state["episode_id"] = "episode-1"
        calls.append("persist")

    async def act(fn, payload, *, timeout_s=120):
        assert payload["episode_id"] == "episode-1"
        assert payload["hitl"]["required"] is True
        calls.append("record_hitl")
        return {"phase": "record_hitl"}

    async def emit(event, **kwargs):
        calls.append("emit")

    async def finalize(outcome):
        calls.append("finalize")

    monkeypatch.setattr(incident, "_ticket_and_notify", ticket_and_notify)
    monkeypatch.setattr(incident, "_persist", persist)
    monkeypatch.setattr(incident, "_act", act)
    monkeypatch.setattr(incident, "_emit", emit)
    monkeypatch.setattr(incident, "_finalize", finalize)

    with pytest.raises(ApplicationError) as exc_info:
        await incident._handoff_to_human(
            reason="missing evidence",
            approval_purpose="investigation",
        )

    # All side-effects ran before the raise
    assert calls == ["ticket_and_notify", "persist", "record_hitl", "emit", "finalize"]

    err = exc_info.value
    assert err.type == "human_required"
    assert err.non_retryable is True
    assert "investigation" in str(err)
    assert incident._phase == "human_handoff_complete"


@pytest.mark.asyncio
async def test_incident_bootstrap_gated(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_INCIDENT_PARITY", raising=False)
    from am_support_agent.orchestrator.activities.incident import bootstrap_incident

    out = await bootstrap_incident({"tracking_id": "t-1", "alert": {}})
    assert out["gated"] is True
    assert out["tracking_id"] == "t-1"
    assert "CapabilityClient" in out["required_ports"]


@pytest.mark.asyncio
async def test_check_parity_gated(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_INCIDENT_PARITY", raising=False)
    from am_support_agent.orchestrator.activities.incident import check_parity

    out = await check_parity({"tracking_id": "t-1"})
    assert out["gated"] is True


@pytest.mark.asyncio
async def test_spt_bootstrap_gated_with_catalog(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPPORT_AGENT_SPT_PARITY", raising=False)
    catalog = tmp_path / "catalog"
    (catalog / "spt").mkdir(parents=True)
    (catalog / "prompts").mkdir()
    (catalog / "spt" / "demo.json").write_text('{"id": "demo"}', encoding="utf-8")
    monkeypatch.setenv("SUPPORT_AGENT_CATALOG_ROOT", str(catalog))

    from am_support_agent.orchestrator.activities.spt import bootstrap_spt

    out = await bootstrap_spt({"demand": {"demand_ref": "d1"}})
    assert out["gated"] is True
    assert out["catalog_preview"]["spt_entry_count"] == 1


def test_worker_registers_parity_workflows():
    from am_support_agent.orchestrator.workflows import (
        AlertIncidentWorkflow,
        SptRunWorkflow,
        SupportA2AWorkflow,
    )

    assert SupportA2AWorkflow.__name__
    assert AlertIncidentWorkflow.__name__
    assert SptRunWorkflow.__name__


def test_resolve_task_queue_keeps_support_agent_v2(monkeypatch):
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "support-agent-v2")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "prod")
    from am_support_agent.orchestrator.queue import resolve_task_queue

    assert resolve_task_queue() == "support-agent-v2"


@pytest.mark.asyncio
async def test_worker_sandbox_accepts_registered_workflows():
    """Fail loud if a workflow pulls sandbox-restricted imports (e.g. httpx)."""
    pytest.importorskip("temporalio")
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from am_support_agent.orchestrator.activities.a2a import execute_plan
    from am_support_agent.orchestrator.activities.incident import INCIDENT_ACTIVITIES
    from am_support_agent.orchestrator.activities.spt import (
        bootstrap_spt,
        resolve_spt_catalog,
    )
    from am_support_agent.orchestrator.workflows import (
        AlertIncidentWorkflow,
        SptRunWorkflow,
        SupportA2AWorkflow,
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        Worker(
            env.client,
            task_queue="support-agent-v2",
            workflows=[SupportA2AWorkflow, AlertIncidentWorkflow, SptRunWorkflow],
            activities=[
                execute_plan,
                *INCIDENT_ACTIVITIES,
                bootstrap_spt,
                resolve_spt_catalog,
            ],
        )
