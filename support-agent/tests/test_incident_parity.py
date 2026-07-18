"""Intelligence, incident acceptance gate, and SPT parity tests."""

from __future__ import annotations

import pytest

from am_support_agent.contracts.capabilities import ObserveEvidence, WorkItemRef
from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.incident import IncidentContext
from am_support_agent.intelligence import (
    ActionPlanner,
    ContextBuilder,
    IncidentValidator,
)
from am_support_agent.learning import ingest_feedback_event, persist_episode, promotion_allowed
from am_support_agent.contracts.incident import IncidentEpisode


def test_validator_fail_closed_without_observe():
    ctx = ContextBuilder().build(
        tracking_id="t1",
        run_ref="r1",
        alert={"service": "payments", "env": "preprod"},
        work_item=WorkItemRef(work_item_ref="wi:1", assignee_ref="u:1"),
        owner=None,
        observe=[],
        similar_incident_ids=[],
        catalog_refs=[],
    )
    v = IncidentValidator().validate(ctx)
    assert v.status == IncidentValidationStatus.INCONCLUSIVE
    assert "observe" in v.missing_evidence


def test_validator_confirmed_with_evidence():
    ctx = ContextBuilder().build(
        tracking_id="t1",
        run_ref="r1",
        alert={"service": "payments", "env": "preprod", "status": "firing"},
        work_item=WorkItemRef(work_item_ref="wi:1", assignee_ref="u:1"),
        owner=None,
        observe=[ObserveEvidence(kind="metrics", status="ok", summary="up")],
        similar_incident_ids=[],
        catalog_refs=[],
    )
    v = IncidentValidator().validate(ctx)
    assert v.status == IncidentValidationStatus.CONFIRMED
    actions = ActionPlanner().plan(validation=v, ctx=ctx)
    assert any(a["capability"] == "chat.message.send" for a in actions)


def test_validator_not_confirmed_on_resolved_alert():
    ctx = ContextBuilder().build(
        tracking_id="t1",
        run_ref="r1",
        alert={"service": "payments", "status": "resolved"},
        work_item=WorkItemRef(work_item_ref="wi:1", assignee_ref="u:1"),
        owner=None,
        observe=[ObserveEvidence(kind="metrics", status="ok")],
        similar_incident_ids=[],
        catalog_refs=[],
    )
    v = IncidentValidator().validate(ctx)
    assert v.status == IncidentValidationStatus.NOT_CONFIRMED


def test_learning_persists_episode_and_feedback():
    ep = persist_episode(
        IncidentEpisode(episode_id="", tracking_id="t-learn", decision="confirmed")
    )
    assert ep.episode_id
    fb = ingest_feedback_event({"episode_id": ep.episode_id, "tracking_id": "t-learn", "rating": "pass"})
    assert fb["accepted"] is True
    assert fb["auto_promote"] is False
    assert promotion_allowed(human_approved=True, offline_eval_passed=True) is True


@pytest.mark.asyncio
async def test_incident_parity_bootstrap(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")

    from am_support_agent.orchestrator.activities.incident import bootstrap_incident

    out = await bootstrap_incident(
        {
            "tracking_id": "trk-parity-1",
            "alert": {
                "service": "payments",
                "env": "preprod",
                "title": "High error rate",
                "status": "firing",
            },
        }
    )
    assert out["gated"] is False
    assert out["continue"] is True
    assert out["validation"]["status"] == "confirmed"
    assert out["episode_id"]


@pytest.mark.asyncio
async def test_incident_parity_inconclusive_without_assign(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")

    from am_support_agent.adapters.capability_client import FakeCapabilityClient
    from am_support_agent.composition import build_runtime
    from am_support_agent.orchestrator.activities import incident as incident_mod

    # Patch runtime to use a client that never assigns
    class NoAssign(FakeCapabilityClient):
        async def call(self, call):  # type: ignore[no-untyped-def]
            if call.capability == "work-item.assign":
                from am_support_agent.ports.capability import CapabilityResult

                return CapabilityResult(ok=True, capability=call.capability, data={})
            if call.capability == "work-item.get":
                from am_support_agent.ports.capability import CapabilityResult

                ref = call.args.get("work_item_ref")
                return CapabilityResult(
                    ok=True,
                    capability=call.capability,
                    data={"work_item_ref": ref, "status": "open", "assignee_ref": ""},
                )
            return await super().call(call)

    rt = build_runtime(mode="test", capability=NoAssign())
    monkeypatch.setattr(incident_mod, "build_runtime", lambda: rt)

    out = await incident_mod.bootstrap_incident(
        {
            "tracking_id": "trk-inc-1",
            "alert": {"service": "payments", "status": "firing"},
        }
    )
    assert out["needs_hitl"] is True
    assert out["validation"]["status"] == "inconclusive"


@pytest.mark.asyncio
async def test_spt_parity_bootstrap(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPPORT_AGENT_SPT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")
    catalog = tmp_path / "catalog"
    (catalog / "spt").mkdir(parents=True)
    (catalog / "prompts").mkdir()
    (catalog / "spt" / "demo.json").write_text('{"id":"demo"}', encoding="utf-8")
    monkeypatch.setenv("SUPPORT_AGENT_CATALOG_ROOT", str(catalog))

    from am_support_agent.orchestrator.activities.spt import bootstrap_spt

    out = await bootstrap_spt({"demand": {"demand_ref": "demo", "sandbox": True}})
    assert out["gated"] is False
    assert out["execute"]["ok"] is True
