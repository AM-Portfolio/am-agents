# am-agents — build & deploy

Same pattern as [am-platform/helm/README.md](../../am-platform/helm/README.md): Docker image per agent, flat `helm/` + **HashiCorp Vault** (not Azure Key Vault).

QA Specs / UI evidence / release-gate live in **[am-qa-agents](https://github.com/AM-Portfolio/am-qa-agents)** (not this repo).

## Agents

| Agent | Image | Port | Ingress path |
|-------|-------|------|--------------|
| db-agent | `ghcr.io/am-portfolio/am-db-agent` | 8140 | `/db` |
| tool-agent | `ghcr.io/am-portfolio/am-tool-agent` | 8141 | `/tools` |
| support-agent | `ghcr.io/am-portfolio/am-support-agent` | 8091 | (in-cluster / as configured) |
| fin-portfolio-agent | (see module) | — | — |

## Environments

| Env | Namespace | Host |
|-----|-----------|------|
| dev | `am-apps-dev` | `am-dev.asrax.in` |
| preprod | `am-apps-preprod` | `am.asrax.in` |
| prod | `am-apps-prod` | `am.asrax.in` |

Helm merge order (CI): `values.yaml` → `vault-mappings.yaml` → `values.{dev|preprod|prod}.yaml`

## Secrets (Vault only — never in git)

1. **Local laptop:** copy `db-agent/.env.example` → `.env.preprod` (gitignored).
2. **Cluster:** seed Vault via [vault-sync.ps1](../../am-platform/automation/scripts/vault-sync.ps1) from `.secrets.{env}.env`.

### Vault paths (reuse existing — no per-agent paths required)

Agents do **not** need dedicated Vault entries. Helm points at paths that already exist from am-platform infra sync.

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

**Plain Helm `env:` (not Vault):** `QDRANT_URL` / `QDRANT_HOST`, `KAFKA_UI_*`, gateway URLs.

Key names must match `helm/vault-mappings.yaml` in each agent. CLI writes use `apps/{env}/...`; Vault Agent reads `apps/data/{env}/...` (KV v2).

## Local Docker build

```bash
cd am-agents/db-agent
docker build -t am-db-agent:local .

cd am-agents/tool-agent
docker build -t am-tool-agent:local .
```

## CI/CD workflows

| Workflow | Trigger |
|----------|---------|
| `.github/workflows/am-db-agent.yml` | push to `db-agent/**` → build + deploy dev → preprod → prod |
| `.github/workflows/am-tool-agent.yml` | push to `tool-agent/**` |
| `.github/workflows/am-support-agent.yml` | push to `support-agent/**` |
| `deploy-am-db-agent.yml` | manual redeploy |
| `deploy-am-support-agent.yml` | manual redeploy |

## Pre-commit

```powershell
cd am-agents
.\scripts\check-no-secrets.ps1
```

## First deploy checklist

1. Confirm shared Vault paths exist (infra + `am-identity` + `am-mcp-gateway`) — see table above
2. Push to `main` (or run manual deploy workflow)
3. Verify pods: `kubectl -n am-apps-preprod get pods | findstr am-db-agent`
4. Health: `curl https://am.asrax.in/db/health`, `curl https://am.asrax.in/tools/health`
5. Confirm secrets come from Vault Agent (`/vault/secrets/*`), not plain `env:` in Deployment

## MCP gateway

Set `DB_AGENT_BASE_URL` in [am-mcp-gateway helm values](../../am-platform/am-mcp-gateway/helm/) per env so gateway can route to db-agent.

Set `TOOL_AGENT_BASE_URL` in the same helm values for the new tool-agent (`http://am-tool-agent.am-apps-{env}.svc.cluster.local:8141`).
