"""Intelligence, incident acceptance gate, remediation memory, and SPT parity tests."""

from __future__ import annotations

import pytest

from am_support_agent.contracts.capabilities import ObserveEvidence, WorkItemRef
from am_support_agent.contracts.enums import IncidentValidationStatus
from am_support_agent.contracts.incident import (
    EvidenceObservation,
    IncidentContext,
    IncidentEpisode,
    RemediationCandidate,
    RemediationStep,
)
from am_support_agent.intelligence import (
    ActionPlanner,
    ContextBuilder,
    IncidentValidator,
    classify_from_evidence,
    evaluate_recovery,
    select_policy,
)
from am_support_agent.learning import ingest_feedback_event, persist_episode, promotion_allowed
from am_support_agent.stores.remediation import (
    clear_memory_store,
    extract_remediation_steps,
    find_matching_candidate,
    upsert_candidate,
)


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


def test_evidence_gate_active_on_unhealthy_metrics():
    policy = select_policy({"alertname": "HighErrorRate"})
    obs = [
        EvidenceObservation(
            kind="metrics",
            transport_ok=True,
            parseable=True,
            healthy=False,
            summary="unhealthy",
            predicates=[],
        )
    ]
    decision = classify_from_evidence(
        alert={"status": "firing", "service": "payments"},
        observations=obs,
        policy=policy,
    )
    assert decision["continue"] is True
    assert decision["decision"] == "active"


def test_evidence_gate_inconclusive_without_parseable_health():
    policy = select_policy({})
    obs = [
        EvidenceObservation(
            kind="metrics",
            transport_ok=True,
            parseable=True,
            healthy=None,
            summary="empty",
            predicates=[],
        )
    ]
    decision = classify_from_evidence(
        alert={"status": "firing"},
        observations=obs,
        policy=policy,
    )
    assert decision["needs_hitl"] is True
    assert decision["status"] == "inconclusive"


def test_transport_ok_alone_never_recovers():
    policy = select_policy({})
    policy = policy.model_copy(update={"recovery_stability_samples": 2})
    batch = [
        EvidenceObservation(
            kind="metrics",
            transport_ok=True,
            parseable=True,
            healthy=None,
            summary="transport only",
        )
    ]
    result = evaluate_recovery(sample_batches=[batch, batch], policy=policy)
    assert result["recovered"] is False


def test_recovery_requires_stable_healthy_batches():
    policy = select_policy({})
    policy = policy.model_copy(update={"recovery_stability_samples": 2})
    healthy = [
        EvidenceObservation(
            kind="metrics",
            transport_ok=True,
            parseable=True,
            healthy=True,
            summary="healthy",
        )
    ]
    result = evaluate_recovery(sample_batches=[healthy, healthy], policy=policy)
    assert result["recovered"] is True


def test_learning_persists_episode_and_feedback():
    ep = persist_episode(
        IncidentEpisode(episode_id="", tracking_id="t-learn", decision="confirmed")
    )
    assert ep.episode_id
    fb = ingest_feedback_event(
        {"episode_id": ep.episode_id, "tracking_id": "t-learn", "rating": "pass"}
    )
    assert fb["accepted"] is True
    assert fb["auto_promote"] is False
    assert promotion_allowed(human_approved=True, offline_eval_passed=True) is True


def test_notification_actions_do_not_create_remediation_candidate():
    clear_memory_store()
    steps = extract_remediation_steps(
        [
            {"capability": "chat.message.send", "ok": True, "args": {"body": "hi"}},
            {"capability": "work-item.comment", "ok": True, "args": {"body": "note"}},
        ]
    )
    assert steps == []


def test_remediation_candidate_roundtrip():
    clear_memory_store()
    cand = upsert_candidate(
        RemediationCandidate(
            service="payments",
            env="dev",
            fingerprint="fp1",
            policy_id="default-firing-v1",
            steps=[
                RemediationStep(
                    capability="secret.inject",
                    args_schema={"name": "restart"},
                    effect="remediation",
                )
            ],
            status="verified",
        )
    )
    assert cand.candidate_id
    hit = find_matching_candidate(
        service="payments",
        env="dev",
        fingerprint="fp1",
        policy_id="default-firing-v1",
    )
    assert hit is not None
    assert hit.steps[0].capability == "secret.inject"


@pytest.mark.asyncio
async def test_incident_parity_bootstrap(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "support-agent-v2")

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
    assert "steps" in out


@pytest.mark.asyncio
async def test_split_activities_order(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")

    from am_support_agent.orchestrator.activities import incident as acts

    norm = await acts.normalize_alert(
        {
            "tracking_id": "trk-split-1",
            "alert": {
                "labels": {"service": "payments", "env": "dev", "alertname": "HighError"},
                "status": "firing",
            },
        }
    )
    mem = await acts.retrieve_memory(
        {"tracking_id": "trk-split-1", "alert": norm["alert"], "policy": norm["policy"]}
    )
    metrics = await acts.query_metrics(
        {"tracking_id": "trk-split-1", "alert": norm["alert"]}
    )
    logs = await acts.query_logs(
        {"tracking_id": "trk-split-1", "alert": norm["alert"]}
    )
    gate = await acts.intelligence_gate(
        {
            "tracking_id": "trk-split-1",
            "alert": norm["alert"],
            "observations": [metrics["observation"], logs["observation"]],
        }
    )
    assert mem["phase"] == "retrieve_memory"
    assert metrics["phase"] == "query_metrics"
    assert logs["phase"] == "query_logs"
    assert gate["continue"] is True

    owner = await acts.resolve_owner(
        {"tracking_id": "trk-split-1", "alert": norm["alert"]}
    )
    created = await acts.create_ticket(
        {"tracking_id": "trk-split-1", "alert": norm["alert"]}
    )
    assigned = await acts.assign_ticket(
        {
            "tracking_id": "trk-split-1",
            "work_item": created["work_item"],
            "owner": owner["owner"],
        }
    )
    notify = await acts.notify_firing(
        {"tracking_id": "trk-split-1", "owner": owner["owner"]}
    )
    assert assigned["work_item"]["assignee_ref"]
    assert notify["ok"] is True

    # Recovery path: refuse close without recovered flag.
    refused = await acts.close_ticket(
        {
            "tracking_id": "trk-split-1",
            "work_item": assigned["work_item"],
            "recovered": False,
        }
    )
    assert refused["ok"] is False

    vmetrics = await acts.verify_metrics(
        {"tracking_id": "trk-split-1", "alert": norm["alert"], "recovery": True}
    )
    vlogs = await acts.verify_logs(
        {"tracking_id": "trk-split-1", "alert": norm["alert"], "recovery": True}
    )
    recovery = await acts.evaluate_recovery_activity(
        {
            "tracking_id": "trk-split-1",
            "alert": norm["alert"],
            "policy": gate["policy"],
            "sample_batches": [
                [vmetrics["observation"], vlogs["observation"]],
                [vmetrics["observation"], vlogs["observation"]],
            ],
        }
    )
    assert recovery["recovered"] is True
    closed = await acts.close_ticket(
        {
            "tracking_id": "trk-split-1",
            "work_item": assigned["work_item"],
            "recovered": True,
        }
    )
    assert closed["ok"] is True


@pytest.mark.asyncio
async def test_silence_feedback_requires_env_service(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")

    from am_support_agent.orchestrator.activities.incident import (
        apply_alert_silence,
        parse_alert_feedback,
    )

    parsed = await parse_alert_feedback(
        {
            "tracking_id": "trk-sil-1",
            "alert": {"service": "payments", "env": "dev"},
            "feedback": {"kind": "silence", "duration_minutes": 30, "requester": "ops"},
        }
    )
    assert parsed["ok"] is True
    assert parsed["needs_approval"] is True
    assert parsed["request"]["matchers"]["env"] == "dev"

    denied = await apply_alert_silence(
        {
            "tracking_id": "trk-sil-1",
            "approved": False,
            "request": parsed["request"],
        }
    )
    assert denied["ok"] is False

    applied = await apply_alert_silence(
        {
            "tracking_id": "trk-sil-1",
            "approved": True,
            "request": parsed["request"],
        }
    )
    assert applied["ok"] is True
    assert applied["silence"]["silence_id"]


@pytest.mark.asyncio
async def test_incident_parity_inconclusive_without_assign(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")

    from am_support_agent.adapters.capability_client import FakeCapabilityClient
    from am_support_agent.composition import build_runtime
    from am_support_agent.orchestrator.activities import incident as incident_mod

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
            "alert": {"service": "payments", "status": "firing", "env": "dev"},
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
