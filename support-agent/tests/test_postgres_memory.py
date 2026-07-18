"""Postgres integration tests for durable incident memory (CI service container)."""

from __future__ import annotations

import os

import pytest

from am_support_agent.contracts.incident import (
    IncidentContext,
    IncidentEpisode,
    IncidentFeedbackEvent,
    MemoryQuery,
    episode_id_for,
)
from am_support_agent.stores.migrations import apply_migrations
from am_support_agent.stores.postgres_episodes import (
    PostgresEpisodeStore,
    PostgresFeedbackStore,
)

DSN = os.getenv("SUPPORT_AGENT_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="SUPPORT_AGENT_DATABASE_URL required for Postgres memory tests",
)


@pytest.fixture(scope="module")
def episode_store() -> PostgresEpisodeStore:
    store = PostgresEpisodeStore(DSN)
    # Idempotent: apply migrations twice
    apply_migrations(store._conn)
    return store


@pytest.fixture(scope="module")
def feedback_store() -> PostgresFeedbackStore:
    return PostgresFeedbackStore(DSN)


def test_idempotent_episode_upsert(episode_store: PostgresEpisodeStore):
    eid = episode_id_for(tracking_id="pg-trk", run_ref="pg-run")
    a = episode_store.upsert(
        IncidentEpisode(
            episode_id=eid,
            tracking_id="pg-trk",
            run_ref="pg-run",
            decision="confirmed",
            outcome="pending",
            context=IncidentContext(
                tracking_id="pg-trk",
                alert={"service": "payments", "env": "ci"},
            ),
        )
    )
    b = episode_store.upsert(
        IncidentEpisode(
            episode_id=eid,
            tracking_id="pg-trk",
            run_ref="pg-run",
            decision="confirmed",
            outcome="pending",
        )
    )
    assert a.episode_id == b.episode_id == eid
    updated = episode_store.update_outcome(eid, outcome="confirmed", verify_status="passed")
    assert updated.outcome == "confirmed"
    assert episode_store.ready() is True


def test_feedback_idempotency(feedback_store: PostgresFeedbackStore, episode_store: PostgresEpisodeStore):
    eid = episode_id_for(tracking_id="pg-fb", run_ref="pg-fb-run")
    episode_store.upsert(
        IncidentEpisode(
            episode_id=eid,
            tracking_id="pg-fb",
            run_ref="pg-fb-run",
            decision="inconclusive",
            outcome="pending",
        )
    )
    a = feedback_store.append(
        IncidentFeedbackEvent(
            episode_id=eid,
            tracking_id="pg-fb",
            kind="hitl",
            auto_promote=True,
            idempotency_key="pg-idem-1",
        )
    )
    b = feedback_store.append(
        IncidentFeedbackEvent(
            episode_id=eid,
            tracking_id="pg-fb",
            kind="hitl",
            auto_promote=True,
            idempotency_key="pg-idem-1",
        )
    )
    assert a.feedback_id == b.feedback_id
    assert a.auto_promote is False
    assert feedback_store.get_by_idempotency("pg-idem-1") is not None


def test_query_newest_first(episode_store: PostgresEpisodeStore):
    episode_store.upsert(
        IncidentEpisode(
            episode_id="pg-old",
            tracking_id="t-old",
            run_ref="r-old",
            created_at="2020-01-01T00:00:00+00:00",
            context=IncidentContext(
                tracking_id="t-old",
                alert={"service": "billing", "env": "ci"},
            ),
            decision="confirmed",
            outcome="confirmed",
        )
    )
    episode_store.upsert(
        IncidentEpisode(
            episode_id="pg-new",
            tracking_id="t-new",
            run_ref="r-new",
            created_at="2025-06-01T00:00:00+00:00",
            context=IncidentContext(
                tracking_id="t-new",
                alert={"service": "billing", "env": "ci"},
            ),
            decision="confirmed",
            outcome="confirmed",
        )
    )
    hits = episode_store.query(MemoryQuery(service="billing", env="ci", limit=5))
    assert hits
    assert hits[0].episode_id == "pg-new"


def test_empty_query_guard(episode_store: PostgresEpisodeStore):
    assert episode_store.query(MemoryQuery(limit=5)) == []


def test_schema_excludes_legacy():
    from am_support_agent.stores.schema import LEGACY_RUNSTORE_TABLES, SUPPORT_AGENT_SCHEMA_SQL

    assert "agent_runs" in LEGACY_RUNSTORE_TABLES
    assert "agent_runs" not in SUPPORT_AGENT_SCHEMA_SQL
