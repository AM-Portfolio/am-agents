# am-agents — build & deploy

Same pattern as [am-platform/helm/README.md](../../am-platform/helm/README.md): Docker image per agent, flat `helm/` + **HashiCorp Vault** (not Azure Key Vault).

## Agents

| Agent | Image | Port | Ingress path |
|-------|-------|------|--------------|
| db-agent | `ghcr.io/am-portfolio/am-db-agent` | 8140 | `/db` |
| tool-agent | `ghcr.io/am-portfolio/am-tool-agent` | 8141 | `/tools` |
| ui-test-agent | `ghcr.io/am-portfolio/am-ui-test-agent` | 8130 | `/ui-test` |

## Environments

| Env | Namespace | Host |
|-----|-----------|------|
| dev | `am-apps-dev` | `am-dev.asrax.in` |
| preprod | `am-apps-preprod` | `am.asrax.in` |
| prod | `am-apps-prod` | `am.asrax.in` |

Helm merge order (CI): `values.yaml` → `vault-mappings.yaml` → `values.{dev|preprod|prod}.yaml`

## Secrets (Vault only — never in git)

1. **Local laptop:** copy `db-agent/.env.example` or `ui-test-agent/.env.example` → `.env.preprod` (gitignored).
2. **Cluster:** seed Vault via [vault-sync.ps1](../../am-platform/automation/scripts/vault-sync.ps1) from `.secrets.{env}.env`.

### Vault paths (reuse existing — no per-agent paths required)

Agents do **not** need dedicated `am-db-agent` / `am-ui-test-agent` Vault entries. Helm points at paths that already exist from am-platform infra sync.

**db-agent** (`helm/vault-mappings.yaml` + `values.{env}.yaml`):

| Vault path | Keys injected |
|------------|---------------|
| `apps/data/{env}/infra/postgres` | `POSTGRES_URL` ← `url` |
| `apps/data/{env}/infra/mongodb` | `MONGODB_URI` ← `url` |
| `apps/data/{env}/infra/redis` | `REDIS_URL` (template from host/port/password) |
| `apps/data/{env}/infra/kafka` | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_USERNAME`, `KAFKA_PASSWORD` |
| `apps/data/{env}/services/am-identity` | `AM_MCP_CLIENT_SECRET` |
| `apps/data/{env}/services/am-mcp-gateway` | `LANGFUSE_*`, `LITELLM_MASTER_KEY` |

**tool-agent** (same infra paths as db-agent; plugin tools under `tool-agent/tools/`):

| Vault path | Keys injected |
|------------|---------------|
| `apps/data/{env}/infra/postgres` | `POSTGRES_URL` ← `url` |
| `apps/data/{env}/infra/mongodb` | `MONGODB_URI` ← `url` |
| `apps/data/{env}/infra/redis` | `REDIS_URL` (template) |
| `apps/data/{env}/infra/kafka` | `KAFKA_*` |
| `apps/data/{env}/services/am-identity` | `AM_MCP_CLIENT_SECRET` |
| `apps/data/{env}/services/am-mcp-gateway` | `LANGFUSE_*`, `LITELLM_MASTER_KEY` |

**ui-test-agent:**

| Vault path | Keys injected |
|------------|---------------|
| `apps/data/{env}/infra/mongodb` | `MONGO_URI` ← `url` |
| `apps/data/{env}/services/am-identity` | `AM_MCP_CLIENT_SECRET` |
| `apps/data/{env}/services/am-mcp-gateway` | `LANGFUSE_*` |

**Plain Helm `env:` (not Vault):** `QDRANT_URL` / `QDRANT_HOST`, `KAFKA_UI_*`, gateway URLs.

Key names must match `helm/vault-mappings.yaml` in each agent. CLI writes use `apps/{env}/...`; Vault Agent reads `apps/data/{env}/...` (KV v2).

## Local Docker build

```bash
cd am-agents/db-agent
docker build -t am-db-agent:local .

cd am-agents/tool-agent
docker build -t am-tool-agent:local .

cd am-agents/ui-test-agent
docker build -t am-ui-test-agent:local .
```

### ui-test-agent base image (faster CI)

Playwright + system deps + `pip install` live in a **cached base image** so app builds only copy `app/` and `scripts/` (~seconds instead of ~15 min).

| Image | Rebuild when |
|-------|----------------|
| `ghcr.io/am-portfolio/am-ui-test-agent-base:latest` | `docker/Dockerfile.ui-test-agent-base` or `ui-test-agent/requirements.txt` change |
| `ghcr.io/am-portfolio/am-ui-test-agent:<run_id>` | any `ui-test-agent/app/**` or `scripts/**` change |

CI: `ensure-base` job in `am-ui-test-agent.yml` pulls or rebuilds base; app `Dockerfile` is a thin layer on top.

Manual base rebuild only:

```bash
cd am-agents
docker build -f docker/Dockerfile.ui-test-agent-base -t ghcr.io/am-portfolio/am-ui-test-agent-base:latest .
docker push ghcr.io/am-portfolio/am-ui-test-agent-base:latest
```

Or run workflow **Build Agent Base Images** in GitHub Actions.

## CI/CD workflows

| Workflow | Trigger |
|----------|---------|
| `.github/workflows/am-db-agent.yml` | push to `db-agent/**` → build + deploy dev → preprod → prod |
| `.github/workflows/am-ui-test-agent.yml` | push to `ui-test-agent/**` |
| `deploy-am-db-agent.yml` | manual redeploy |
| `deploy-am-ui-test-agent.yml` | manual redeploy |

## Pre-commit

```powershell
cd am-agents
.\scripts\check-no-secrets.ps1
```

## First deploy checklist

1. Confirm shared Vault paths exist (infra + `am-identity` + `am-mcp-gateway`) — see table above
2. Push to `main` (or run manual deploy workflow)
3. Verify pods: `kubectl -n am-apps-preprod get pods | findstr am-db-agent`
4. Health: `curl https://am.asrax.in/db/health`, `curl https://am.asrax.in/ui-test/health`
5. Confirm secrets come from Vault Agent (`/vault/secrets/*`), not plain `env:` in Deployment

## MCP gateway

Set `DB_AGENT_BASE_URL` in [am-mcp-gateway helm values](../../am-platform/am-mcp-gateway/helm/) per env so gateway can route to db-agent.

Set `TOOL_AGENT_BASE_URL` in the same helm values for the new tool-agent (`http://am-tool-agent.am-apps-{env}.svc.cluster.local:8141`).
