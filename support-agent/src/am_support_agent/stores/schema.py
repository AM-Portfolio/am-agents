"""Dedicated A2A Postgres schema for support-agent (not legacy agent_runs).

Table: support_agent.task_runs
Never maps to libs/platform-adapters PostgresRunStore / agent_runs.
"""

from __future__ import annotations

# Applied by PostgresTaskRunStore._init_schema
SUPPORT_AGENT_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS support_agent;

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

# Forbidden legacy identifiers — tests assert we never target these.
LEGACY_RUNSTORE_TABLES = frozenset({"agent_runs", "agent_run_steps"})

A2A_POSTGRES_TABLE = "support_agent.task_runs"
