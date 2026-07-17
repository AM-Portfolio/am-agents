# Postgres RunStore

Tables `agent_runs` + `agent_run_steps` on database **`agent_platform`** (shared `postgresql.infra`).

## Apply schema

```bash
kubectl -n infra exec -i postgresql-0 -c postgresql -- \
  psql -U postgres -d agent_platform < schema.sql
```

## Env

```text
RUN_STORE_PROVIDER=postgres
RUN_STORE_DSN=postgresql://agent_platform:agent_platform_2026@localhost:5432/agent_platform
# in-cluster:
# RUN_STORE_DSN=postgresql://agent_platform:agent_platform_2026@postgresql.infra.svc.cluster.local:5432/agent_platform
```

Local port-forward: `kubectl -n infra port-forward svc/postgresql 5432:5432`
