# Memory mapping

| Layer | Backing today | Owner today | Parallel v2 rule |
|-------|---------------|-------------|------------------|
| Episodic (A2A tasks) | Memory / SQLite / dedicated Postgres `support_agent.task_runs` | support-agent | See [docs/run-store.md](../docs/run-store.md); never legacy `agent_runs` |
| Episodic (incident ops) | Memory / Postgres `support_agent.incident_episodes` | support-agent | Dedicated logical DB `am_support_agent_{env}`; never overload `task_runs` or legacy `agent_runs` |
| Feedback | Memory / Postgres `support_agent.incident_feedback_events` | support-agent | Idempotent; `auto_promote` always false |
| Workflow ledger | Memory / Postgres `workflow_runs` / `workflow_steps` | support-agent | Distinct from A2A and legacy ledgers |
| Artifacts / docs | MinIO (+ GDrive failover) | `libs/platform-adapters` | Prefix boundary `support-agent-v2/` via `adapters/storage.py` |
| Procedural | `catalog/prompts`, `catalog/verify`, `catalog/spt` | catalog data | Read-only via `intelligence/catalog.py` until promotion gate owns writes |
| Semantic embeddings | Qdrant inside tool/db/ui-test agents | agent-local | **No platform Qdrant / pgvector** in first production release |

## Env

| Variable | Values | Notes |
|----------|--------|-------|
| `SUPPORT_AGENT_EPISODE_STORE` | `memory` \| `postgres` | Falls back to `SUPPORT_AGENT_RUNSTORE` |
| `SUPPORT_AGENT_FEEDBACK_STORE` | `memory` \| `postgres` | Same DSN as episodes |
| `SUPPORT_AGENT_WORKFLOW_STORE` | `memory` \| `postgres` | Same DSN |
| `SUPPORT_AGENT_DATABASE_URL` | Postgres DSN | Vault-injected in preprod/prod |
| `SUPPORT_AGENT_EPISODE_RETENTION_DAYS` | int (default 90) | Terminal episode/feedback purge window |

## Retention

```bash
python -m am_support_agent.stores.retention --days 90 --batch-size 500
```

Audit/promotion tables are **not** purged by this job.

## Advisory rule

Memory informs planning; **live specialist tools** remain authoritative for current system state.
