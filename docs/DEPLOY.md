# am-agents — build & deploy

Same pattern as [am-platform/helm/README.md](../../am-platform/helm/README.md): Docker image per agent, flat `helm/` + **HashiCorp Vault** (not Azure Key Vault).

## Agents

| Agent | Image | Port | Ingress path |
|-------|-------|------|--------------|
| db-agent | `ghcr.io/am-portfolio/am-db-agent` | 8140 | `/db` |
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

### Vault paths to seed

**Infra (reuse existing):**
- `apps/data/{env}/infra/postgres`
- `apps/data/{env}/infra/mongodb`
- `apps/data/{env}/infra/redis`
- `apps/data/{env}/infra/kafka`
- `apps/data/{env}/infra/qdrant`
- `apps/data/{env}/infra/influxdb`

**Services (new):**
- `apps/data/{env}/services/am-db-agent` — `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, optional `LITELLM_MASTER_KEY`, `GRAFANA_*`
- `apps/data/{env}/services/am-ui-test-agent` — `LANGFUSE_*`, optional `TEST_USER_PASSWORD`

**Shared identity:**
- `apps/data/{env}/services/am-identity` — `AM_MCP_CLIENT_SECRET`

Key names must match `helm/vault-mappings.yaml` in each agent.

## Local Docker build

```bash
cd am-agents/db-agent
docker build -t am-db-agent:local .

cd am-agents/ui-test-agent
docker build -t am-ui-test-agent:local .
```

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

1. Seed Vault paths above for target env
2. Push to `main` (or run manual deploy workflow)
3. Verify pods: `kubectl -n am-apps-preprod get pods | findstr am-db-agent`
4. Health: `curl https://am.asrax.in/db/health`, `curl https://am.asrax.in/ui-test/health`
5. Confirm secrets come from Vault Agent (`/vault/secrets/*`), not plain `env:` in Deployment

## MCP gateway

Set `DB_AGENT_BASE_URL` in [am-mcp-gateway helm values](../../am-platform/am-mcp-gateway/helm/) per env so gateway can route to db-agent.
