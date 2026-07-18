-- Agent platform RunStore (ADR-005)
-- Database: agent_platform

CREATE TABLE IF NOT EXISTS agent_runs (
    run_ref                   TEXT PRIMARY KEY,
    kind                      TEXT NOT NULL,
    status                    TEXT NOT NULL,
    parent_run_ref            TEXT NULL,
    incident_ref              TEXT NULL,
    ticket_ref                TEXT NULL,
    demand_ref                TEXT NULL,
    workflow_id               TEXT NULL,
    requested_selector_hash   TEXT NULL,
    summary_json              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs (status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_incident ON agent_runs (incident_ref);
CREATE INDEX IF NOT EXISTS idx_agent_runs_parent ON agent_runs (parent_run_ref);

CREATE TABLE IF NOT EXISTS agent_run_steps (
    step_ref                  TEXT PRIMARY KEY,
    run_ref                   TEXT NOT NULL REFERENCES agent_runs (run_ref) ON DELETE CASCADE,
    name                      TEXT NOT NULL,
    check_ref                 TEXT NULL,
    status                    TEXT NOT NULL,
    claim_lease_until         TIMESTAMPTZ NULL,
    worker_id                 TEXT NULL,
    attempts                  INT NOT NULL DEFAULT 0,
    last_error_class          TEXT NULL,
    result_ref                TEXT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run ON agent_run_steps (run_ref);
CREATE INDEX IF NOT EXISTS idx_agent_run_steps_claim
    ON agent_run_steps (status, claim_lease_until)
    WHERE status IN ('pending', 'claimed');
