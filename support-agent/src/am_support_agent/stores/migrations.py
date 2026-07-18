"""Versioned support_agent schema migrations (idempotent, advisory-locked)."""

from __future__ import annotations

from typing import Sequence

# Migration 1: A2A task ledger (existing)
MIGRATION_001_TASK_RUNS = """
CREATE SCHEMA IF NOT EXISTS support_agent;

CREATE TABLE IF NOT EXISTS support_agent.schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS support_agent.task_runs (
    task_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    op TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT,
    request_json TEXT NOT NULL,
    result_json TEXT,
    feedback_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS support_agent_task_runs_agent_idempotency
    ON support_agent.task_runs (agent_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
"""

# Migration 2: durable incident episodes + feedback + workflow ledger + learning audit
MIGRATION_002_INCIDENT_MEMORY = """
CREATE TABLE IF NOT EXISTS support_agent.incident_episodes (
    episode_id TEXT PRIMARY KEY,
    tracking_id TEXT NOT NULL,
    run_ref TEXT NOT NULL DEFAULT '',
    service TEXT NOT NULL DEFAULT '',
    env TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT '',
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    verify_status TEXT NOT NULL DEFAULT '',
    body_json JSONB NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS incident_episodes_tracking
    ON support_agent.incident_episodes (tracking_id);
CREATE INDEX IF NOT EXISTS incident_episodes_run_ref
    ON support_agent.incident_episodes (run_ref)
    WHERE run_ref <> '';
CREATE INDEX IF NOT EXISTS incident_episodes_lookup
    ON support_agent.incident_episodes (service, env, fingerprint, created_at DESC);
CREATE INDEX IF NOT EXISTS incident_episodes_labels_gin
    ON support_agent.incident_episodes USING GIN (labels);
CREATE UNIQUE INDEX IF NOT EXISTS incident_episodes_tracking_run
    ON support_agent.incident_episodes (tracking_id, run_ref)
    WHERE run_ref <> '';

CREATE TABLE IF NOT EXISTS support_agent.incident_feedback_events (
    feedback_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL DEFAULT '',
    tracking_id TEXT NOT NULL DEFAULT '',
    run_ref TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'outcome',
    rating TEXT NOT NULL DEFAULT '',
    labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    auto_promote BOOLEAN NOT NULL DEFAULT FALSE,
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS incident_feedback_episode
    ON support_agent.incident_feedback_events (episode_id, created_at);
CREATE INDEX IF NOT EXISTS incident_feedback_tracking
    ON support_agent.incident_feedback_events (tracking_id)
    WHERE tracking_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS incident_feedback_idempotency
    ON support_agent.incident_feedback_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS support_agent.workflow_runs (
    run_ref TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    tracking_id TEXT NOT NULL DEFAULT '',
    workflow_id TEXT NOT NULL DEFAULT '',
    parent_run_ref TEXT,
    demand_ref TEXT NOT NULL DEFAULT '',
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_runs_workflow_id
    ON support_agent.workflow_runs (workflow_id)
    WHERE workflow_id <> '';
CREATE INDEX IF NOT EXISTS workflow_runs_tracking
    ON support_agent.workflow_runs (tracking_id)
    WHERE tracking_id <> '';
CREATE INDEX IF NOT EXISTS workflow_runs_parent
    ON support_agent.workflow_runs (parent_run_ref)
    WHERE parent_run_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS support_agent.workflow_steps (
    step_ref TEXT PRIMARY KEY,
    run_ref TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    result_ref TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_steps_run_ref
    ON support_agent.workflow_steps (run_ref, created_at);

CREATE TABLE IF NOT EXISTS support_agent.learning_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL DEFAULT '',
    tracking_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    score DOUBLE PRECISION,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS support_agent.learning_candidates (
    candidate_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'policy',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS support_agent.promotion_decisions (
    decision_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    human_approved BOOLEAN NOT NULL DEFAULT FALSE,
    offline_eval_passed BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Migration 3: durable agent-work event outbox for enterprise dashboards
MIGRATION_003_AGENT_WORK_OUTBOX = """
CREATE TABLE IF NOT EXISTS support_agent.agent_work_event_outbox (
    event_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    workflow_id TEXT NOT NULL DEFAULT '',
    workflow_run_id TEXT NOT NULL DEFAULT '',
    run_ref TEXT NOT NULL DEFAULT '',
    tracking_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT '',
    event_json JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_by TEXT,
    locked_until TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS agent_work_outbox_undelivered
    ON support_agent.agent_work_event_outbox (available_at)
    WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS agent_work_outbox_workflow
    ON support_agent.agent_work_event_outbox (workflow_id, occurred_at);
CREATE INDEX IF NOT EXISTS agent_work_outbox_tracking
    ON support_agent.agent_work_event_outbox (tracking_id, occurred_at);
CREATE INDEX IF NOT EXISTS agent_work_outbox_run_ref
    ON support_agent.agent_work_event_outbox (run_ref, occurred_at);
"""

MIGRATIONS: Sequence[tuple[int, str, str]] = (
    (1, "task_runs", MIGRATION_001_TASK_RUNS),
    (2, "incident_memory", MIGRATION_002_INCIDENT_MEMORY),
    (3, "agent_work_outbox", MIGRATION_003_AGENT_WORK_OUTBOX),
)

# Advisory lock key unique to support-agent migrations
MIGRATION_LOCK_KEY = 0x5A5A_A6E7_1002

# Forbidden legacy identifiers — tests assert we never target these.
LEGACY_RUNSTORE_TABLES = frozenset({"agent_runs", "agent_run_steps"})

A2A_POSTGRES_TABLE = "support_agent.task_runs"
EPISODE_POSTGRES_TABLE = "support_agent.incident_episodes"
FEEDBACK_POSTGRES_TABLE = "support_agent.incident_feedback_events"


def apply_migrations(conn) -> list[int]:
    """Apply pending migrations under a Postgres advisory lock. Returns applied versions."""
    applied: list[int] = []
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            cur.execute(
                """
                CREATE SCHEMA IF NOT EXISTS support_agent;
                CREATE TABLE IF NOT EXISTS support_agent.schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute("SELECT version FROM support_agent.schema_migrations")
            done = {int(row[0] if not isinstance(row, dict) else row["version"]) for row in cur.fetchall()}
            for version, name, sql in MIGRATIONS:
                if version in done:
                    continue
                cur.execute(sql)
                cur.execute(
                    """
                    INSERT INTO support_agent.schema_migrations (version, name)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (version, name),
                )
                applied.append(version)
            conn.commit()
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
    return applied


# Backward-compatible alias used by PostgresTaskRunStore
SUPPORT_AGENT_SCHEMA_SQL = (
    MIGRATION_001_TASK_RUNS
    + "\n"
    + MIGRATION_002_INCIDENT_MEMORY
    + "\n"
    + MIGRATION_003_AGENT_WORK_OUTBOX
)
