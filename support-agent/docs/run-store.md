# Run-store backends

Support-agent owns an **A2A task ledger** (`TaskRunStore`) separate from the
legacy incident ops ledger.

## Supported backends

| `SUPPORT_AGENT_RUNSTORE` | Use | Multi-replica |
|--------------------------|-----|---------------|
| `memory` (default) | Unit tests, single-process local | No |
| `sqlite` | Local/CI durable shadow runs | No (file lock) |
| `postgres` | Dedicated A2A schema `support_agent.task_runs` | Yes (with HA Postgres) |

Env:

- `SUPPORT_AGENT_SQLITE_PATH` — SQLite path (default `/data/support-agent-runs.db`)
- `SUPPORT_AGENT_DATABASE_URL` (or `DATABASE_URL`) — required for postgres
- Optional install: `pip install 'am-support-agent[postgres]'` (psycopg)

## Dedicated A2A Postgres schema

DDL lives in `src/am_support_agent/stores/schema.py` and creates:

- Schema: `support_agent`
- Table: `support_agent.task_runs`
- Unique index on `(agent_id, idempotency_key)` where key is present

This is **not** `public.agent_runs` / `agent_run_steps` from
`libs/platform-adapters` `PostgresRunStore`.

## Workflow run ledger (incident / SPT)

Separate from A2A `task_runs`. Implementation:

- `src/am_support_agent/stores/workflow_ledger.py`
- Env `SUPPORT_AGENT_WORKFLOW_STORE` (`memory` | `sqlite`; postgres pending)
- Defaults to `SUPPORT_AGENT_RUNSTORE` when unset

Tracks parent/child runs, steps, evidence refs, and validation snapshots for
`AlertIncident` / `SPT` / handoff — never overloads A2A or legacy ledgers.

Gateway endpoints:

- `POST /v2/workflows/alert-incident`
- `POST /v2/workflows/spt`
- `POST /v2/workflows/{id}/signals/{name}` (`approve`, `alert.resolved`, `alert.refired`)
- `GET /v2/workflows/{id}/status`
- `POST /v2/handoff`

## Legacy Postgres gap (intentional)

`libs/platform-ports` `RunStore` and `libs/platform-adapters`
`PostgresRunStore` model **agent_runs / agent_run_steps** (`AgentRun`,
`CreateRunRequest`, claim/lease steps). That contract does **not** map cleanly
onto A2A `TaskRequest` / `TaskResult` / idempotency keys / feedback append.

Support-agent therefore:

1. Implements its own `PostgresTaskRunStore` on `support_agent.task_runs`, and
2. Refuses to pretend legacy `agent_runs` is an A2A ledger
   (`legacy_postgres_runstore_compatible() is False`).

Misconfig without a DSN fails fast with a clear `RuntimeError`.
