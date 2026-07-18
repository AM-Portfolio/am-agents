# Memory mapping

| Layer | Backing today | Owner today | Parallel v2 rule |
|-------|---------------|-------------|------------------|
| Episodic (A2A tasks) | Memory / SQLite / dedicated Postgres `support_agent.task_runs` | support-agent | See [docs/run-store.md](../docs/run-store.md); never legacy `agent_runs` |
| Episodic (incident ops) | Postgres RunStore (`agent_runs`, `agent_run_steps`) | `libs/platform-adapters` | Unchanged; do not overload for A2A task ledger |
| Artifacts / docs | MinIO (+ GDrive failover) | `libs/platform-adapters` | Prefix boundary `support-agent-v2/` via `adapters/storage.py` |
| Procedural | `catalog/prompts`, `catalog/verify`, `catalog/spt` | catalog data | Read-only via `intelligence/catalog.py` until promotion gate owns writes |
| Semantic embeddings | Qdrant inside tool/db/ui-test agents | agent-local | **No platform Qdrant** until ownership ADR |

## Advisory rule

Memory informs planning; **live specialist tools** remain authoritative for current system state.
