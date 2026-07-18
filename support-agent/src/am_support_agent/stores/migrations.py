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

# Migration 4: Grafana lifecycle / ticket / familiar-type read models
MIGRATION_004_LIFECYCLE_VIEWS = """
CREATE OR REPLACE VIEW support_agent.v_incident_lifecycle AS
SELECT
    r.run_ref,
    r.tracking_id,
    r.workflow_id,
    r.kind,
    r.status AS ledger_status,
    COALESCE(r.summary->>'phase', '') AS phase,
    COALESCE(r.summary->>'agent_status', '') AS agent_status,
    COALESCE(r.summary->>'final_status', 'open') AS final_status,
    COALESCE(r.summary->>'ticket_ref', '') AS ticket_ref,
    COALESCE(r.summary->>'ticket_url', '') AS ticket_url,
    COALESCE(r.summary->>'ticket_status', 'none') AS ticket_status,
    COALESCE(r.summary->>'assignee_ref', '') AS assignee_ref,
    COALESCE(r.summary->>'assignee_name', '') AS assignee_name,
    COALESCE(r.summary->>'assignee_email', '') AS assignee_email,
    COALESCE(r.summary->>'chat_sent', 'skipped') AS chat_sent,
    COALESCE(r.summary->>'mail_sent', 'n/a') AS mail_sent,
    COALESCE(r.summary->>'familiar_type', '') AS familiar_type,
    COALESCE(r.summary->>'alert_fingerprint', '') AS alert_fingerprint,
    COALESCE(r.summary->>'hitl_state', '') AS hitl_state,
    COALESCE(r.summary->>'approval_purpose', '') AS approval_purpose,
    COALESCE(r.summary->>'known_fix', '') AS known_fix,
    COALESCE((r.summary->>'solved')::boolean, FALSE) AS solved,
    COALESCE(r.summary->>'temporal_run_id', '') AS temporal_run_id,
    COALESCE(r.summary->>'temporal_url', '') AS temporal_url,
    COALESCE(r.summary->>'alert_url', '') AS alert_url,
    COALESCE(r.summary->>'langfuse_url', '') AS langfuse_url,
    COALESCE(r.summary->>'trace_id', '') AS trace_id,
    COALESCE(r.summary->>'langfuse_trace_id', '') AS langfuse_trace_id,
    COALESCE(
        NULLIF(r.summary->>'generator_url', ''),
        e.body_json#>>'{context,alert,generator_url}',
        e.body_json#>>'{context,alert,generatorURL}',
        ''
    ) AS generator_url,
    COALESCE(r.summary->'activities', '{}'::jsonb) AS activities,
    COALESCE(r.summary->'side_effects', '{}'::jsonb) AS side_effects,
    -- Flat incident details for Grafana tables
    COALESCE(
        e.labels->>'alertname',
        split_part(COALESCE(r.summary->>'familiar_type', ''), '|', 1),
        ''
    ) AS alertname,
    COALESCE(e.labels->>'severity', e.body_json->'labels'->>'severity', '') AS severity,
    COALESCE(
        NULLIF(e.service, ''),
        e.labels->>'service',
        e.labels->>'application',
        e.labels->>'app',
        ''
    ) AS service,
    COALESCE(
        e.labels->>'namespace',
        e.body_json->'labels'->>'namespace',
        ''
    ) AS namespace,
    COALESCE(NULLIF(e.env, ''), e.labels->>'env', e.labels->>'environment', '') AS env,
    COALESCE(
        e.body_json->'context'->>'summary',
        e.body_json->>'summary',
        e.labels->>'alertname',
        r.summary->>'familiar_type',
        ''
    ) AS alert_summary,
    COALESCE(e.decision, '') AS decision,
    COALESCE(e.outcome, '') AS episode_outcome,
    COALESCE(e.verify_status, '') AS verify_status,
    COALESCE(e.fingerprint, r.summary->>'alert_fingerprint', '') AS fingerprint,
    (
        SELECT string_agg(
            key || '=' || CASE
                WHEN coalesce((value->>'ok')::boolean, TRUE) THEN 'ok'
                ELSE 'fail'
            END,
            ', '
            ORDER BY key
        )
        FROM jsonb_each(COALESCE(r.summary->'activities', '{}'::jsonb)) AS t(key, value)
    ) AS activities_summary,
    (
        SELECT string_agg(key || '=' || value, ', ' ORDER BY key)
        FROM jsonb_each_text(COALESCE(r.summary->'side_effects', '{}'::jsonb)) AS t(key, value)
    ) AS side_effects_summary,
    COALESCE(fb.feedback_count, 0) AS feedback_count,
    fb.latest_feedback_at,
    e.episode_id,
    e.service AS episode_service,
    e.env AS episode_env,
    r.created_at,
    r.updated_at
FROM support_agent.workflow_runs r
LEFT JOIN LATERAL (
    SELECT
        ep.episode_id,
        ep.outcome,
        ep.service,
        ep.env,
        ep.decision,
        ep.verify_status,
        ep.fingerprint,
        ep.labels,
        ep.body_json
    FROM support_agent.incident_episodes ep
    WHERE ep.tracking_id = r.tracking_id
    ORDER BY ep.updated_at DESC
    LIMIT 1
) e ON TRUE
LEFT JOIN LATERAL (
    SELECT
        count(*)::int AS feedback_count,
        max(f.created_at) AS latest_feedback_at
    FROM support_agent.incident_feedback_events f
    WHERE f.tracking_id = r.tracking_id
) fb ON TRUE;

CREATE OR REPLACE VIEW support_agent.v_ticket_status AS
SELECT
    ticket_ref,
    tracking_id,
    run_ref,
    workflow_id,
    alertname,
    severity,
    service,
    namespace,
    env,
    alert_summary,
    familiar_type,
    alert_fingerprint,
    agent_status,
    final_status,
    phase,
    ticket_status,
    assignee_ref,
    assignee_name,
    assignee_email,
    chat_sent,
    mail_sent,
    decision,
    episode_outcome,
    verify_status,
    CASE WHEN feedback_count > 0 THEN TRUE ELSE FALSE END AS feedback_received,
    feedback_count,
    hitl_state,
    approval_purpose,
    known_fix,
    activities_summary,
    side_effects_summary,
    activities,
    side_effects,
    updated_at,
    created_at
FROM support_agent.v_incident_lifecycle
WHERE ticket_ref <> ''
ORDER BY updated_at DESC;

CREATE OR REPLACE VIEW support_agent.v_unsolved_incidents AS
SELECT *
FROM support_agent.v_incident_lifecycle
WHERE COALESCE(final_status, 'open') NOT IN ('recovered', 'closed')
ORDER BY updated_at DESC;

CREATE OR REPLACE VIEW support_agent.v_familiar_type_summary AS
SELECT
    COALESCE(NULLIF(familiar_type, ''), 'unknown') AS familiar_type,
    count(*)::int AS incident_count,
    count(*) FILTER (
        WHERE COALESCE(final_status, 'open') NOT IN ('recovered', 'closed')
    )::int AS unsolved_count,
    count(*) FILTER (
        WHERE final_status IN ('recovered', 'closed')
    )::int AS solved_count,
    count(*) FILTER (
        WHERE final_status = 'human_required' OR hitl_state <> ''
    )::int AS hitl_count,
    max(updated_at) AS latest_updated_at,
    (array_agg(tracking_id ORDER BY updated_at DESC))[1] AS latest_tracking_id,
    (array_agg(NULLIF(ticket_ref, '') ORDER BY updated_at DESC)
        FILTER (WHERE ticket_ref <> ''))[1] AS latest_ticket_ref,
    (array_agg(agent_status ORDER BY updated_at DESC))[1] AS latest_agent_status,
    (array_agg(final_status ORDER BY updated_at DESC))[1] AS latest_final_status,
    (array_agg(NULLIF(alertname, '') ORDER BY updated_at DESC)
        FILTER (WHERE alertname <> ''))[1] AS latest_alertname,
    (array_agg(NULLIF(severity, '') ORDER BY updated_at DESC)
        FILTER (WHERE severity <> ''))[1] AS latest_severity,
    (array_agg(NULLIF(assignee_name, '') ORDER BY updated_at DESC)
        FILTER (WHERE assignee_name <> ''))[1] AS latest_assignee_name,
    (array_agg(NULLIF(assignee_ref, '') ORDER BY updated_at DESC)
        FILTER (WHERE assignee_ref <> ''))[1] AS latest_assignee_ref
FROM support_agent.v_incident_lifecycle
GROUP BY COALESCE(NULLIF(familiar_type, ''), 'unknown');
"""

# Migration 5: recreate lifecycle views with assignee columns (DROP required).
MIGRATION_005_ASSIGNEE_VIEWS = """
DROP VIEW IF EXISTS support_agent.v_familiar_type_summary;
DROP VIEW IF EXISTS support_agent.v_unsolved_incidents;
DROP VIEW IF EXISTS support_agent.v_ticket_status;
DROP VIEW IF EXISTS support_agent.v_incident_lifecycle;
""" + MIGRATION_004_LIFECYCLE_VIEWS + """
GRANT SELECT ON support_agent.v_incident_lifecycle TO alert_ops_ro;
GRANT SELECT ON support_agent.v_ticket_status TO alert_ops_ro;
GRANT SELECT ON support_agent.v_unsolved_incidents TO alert_ops_ro;
GRANT SELECT ON support_agent.v_familiar_type_summary TO alert_ops_ro;
"""

# Migration 6: link deep-link columns (temporal/alert/langfuse) on lifecycle views.
MIGRATION_006_LINK_VIEWS = MIGRATION_005_ASSIGNEE_VIEWS

MIGRATIONS: Sequence[tuple[int, str, str]] = (
    (1, "task_runs", MIGRATION_001_TASK_RUNS),
    (2, "incident_memory", MIGRATION_002_INCIDENT_MEMORY),
    (3, "agent_work_outbox", MIGRATION_003_AGENT_WORK_OUTBOX),
    (4, "lifecycle_views", MIGRATION_004_LIFECYCLE_VIEWS),
    (5, "assignee_views", MIGRATION_005_ASSIGNEE_VIEWS),
    (6, "link_views", MIGRATION_006_LINK_VIEWS),
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
    + "\n"
    + MIGRATION_004_LIFECYCLE_VIEWS
)
