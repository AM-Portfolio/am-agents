"""Durable episode/feedback memory store tests."""

from __future__ import annotations

from am_support_agent.contracts.incident import (
    IncidentContext,
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
    episode_id_for,
)
from am_support_agent.learning import ingest_feedback_event, persist_episode
from am_support_agent.learning.offline import evaluate_episode, record_promotion
from am_support_agent.stores.episodes import MemoryEpisodeStore, MemoryFeedbackStore


def test_empty_query_returns_nothing():
    store = MemoryEpisodeStore()
    store.append(
        IncidentEpisode(
            episode_id="ep-1",
            tracking_id="t1",
            run_ref="r1",
            context=IncidentContext(
                tracking_id="t1",
                alert={"service": "payments", "env": "preprod"},
            ),
            decision="confirmed",
            outcome="confirmed",
        )
    )
    assert store.query(MemoryQuery(limit=5)) == []


def test_idempotent_upsert_and_outcome():
    store = MemoryEpisodeStore()
    eid = episode_id_for(tracking_id="trk", run_ref="run")
    a = store.upsert(
        IncidentEpisode(
            episode_id=eid,
            tracking_id="trk",
            run_ref="run",
            decision="confirmed",
            outcome="pending",
        )
    )
    b = store.upsert(
        IncidentEpisode(
            episode_id=eid,
            tracking_id="trk",
            run_ref="run",
            decision="confirmed",
            outcome="pending",
        )
    )
    assert a.episode_id == b.episode_id == eid
    updated = store.update_outcome(eid, outcome="confirmed", verify_status="passed")
    assert updated.outcome == "confirmed"
    assert updated.verify_status == "passed"


def test_query_newest_first_and_filter():
    store = MemoryEpisodeStore()
    store.append(
        IncidentEpisode(
            episode_id="ep-old",
            tracking_id="t1",
            run_ref="r1",
            created_at="2020-01-01T00:00:00+00:00",
            context=IncidentContext(
                tracking_id="t1",
                alert={"service": "payments", "env": "preprod"},
            ),
            decision="confirmed",
        )
    )
    store.append(
        IncidentEpisode(
            episode_id="ep-new",
            tracking_id="t2",
            run_ref="r2",
            created_at="2025-01-01T00:00:00+00:00",
            context=IncidentContext(
                tracking_id="t2",
                alert={"service": "payments", "env": "preprod"},
            ),
            decision="confirmed",
        )
    )
    hits = store.query(MemoryQuery(service="payments", env="preprod", limit=5))
    assert [h.episode_id for h in hits] == ["ep-new", "ep-old"]


def test_feedback_idempotency_and_no_auto_promote():
    store = MemoryFeedbackStore()
    a = store.append(
        IncidentFeedbackEvent(
            episode_id="ep-1",
            tracking_id="t1",
            kind="hitl",
            auto_promote=True,
            idempotency_key="k1",
        )
    )
    b = store.append(
        IncidentFeedbackEvent(
            episode_id="ep-1",
            tracking_id="t1",
            kind="hitl",
            auto_promote=True,
            idempotency_key="k1",
        )
    )
    assert a.feedback_id == b.feedback_id
    assert a.auto_promote is False


def test_persist_and_learning_pipeline():
    ep = persist_episode(
        IncidentEpisode(
            episode_id="",
            tracking_id="t-learn",
            run_ref="r-learn",
            decision="confirmed",
            outcome="confirmed",
            context=IncidentContext(
                tracking_id="t-learn",
                alert={"service": "billing", "token": "secret-value"},
            ),
        )
    )
    assert ep.episode_id
    assert ep.context and ep.context.alert.get("token") == "[REDACTED]"
    fb = ingest_feedback_event(
        {
            "episode_id": ep.episode_id,
            "tracking_id": "t-learn",
            "kind": "hitl",
            "outcome": "hitl_approved",
            "idempotency_key": "fb-1",
            "payload": {"approved": True},
        }
    )
    assert fb["accepted"] is True
    assert fb["auto_promote"] is False
    eval_out = evaluate_episode(ep.episode_id)
    assert eval_out["ok"] is True
    promo = record_promotion(
        candidate_id="cand-1",
        human_approved=True,
        offline_eval_passed=True,
    )
    assert promo["allowed"] is True
    assert promo["promoted"] is False


def test_schema_never_targets_legacy():
    from am_support_agent.stores.schema import LEGACY_RUNSTORE_TABLES, SUPPORT_AGENT_SCHEMA_SQL

    assert "agent_runs" in LEGACY_RUNSTORE_TABLES
    assert "agent_runs" not in SUPPORT_AGENT_SCHEMA_SQL
    assert "incident_episodes" in SUPPORT_AGENT_SCHEMA_SQL


def test_retention_purges_terminal_only():
    store = MemoryEpisodeStore()
    store.append(
        IncidentEpisode(
            episode_id="ep-old-term",
            tracking_id="t-old",
            run_ref="r-old",
            created_at="2000-01-01T00:00:00+00:00",
            decision="confirmed",
            outcome="confirmed",
        )
    )
    store.append(
        IncidentEpisode(
            episode_id="ep-pending",
            tracking_id="t-pend",
            run_ref="r-pend",
            created_at="2000-01-01T00:00:00+00:00",
            decision="confirmed",
            outcome="pending",
        )
    )
    deleted = store.purge_terminal_before("2010-01-01T00:00:00+00:00", limit=50)
    assert deleted == 1
    assert store.get("ep-pending") is not None
    assert store.get("ep-old-term") is None
