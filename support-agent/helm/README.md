# Support-agent Helm values for am-pipelines universal-chart

Canonical deploy path (central-build-publish → central-deploy):

```text
support-agent/helm/values.yaml
support-agent/helm/values.<env>.yaml
```

The standalone chart under `deploy/helm/` remains for local lint/render and
PVC experiments. Production publish uses the universal chart + companion worker.

Companion worker:

| Key | Purpose |
|-----|---------|
| `companionWorker.enabled` | Deploy `{{release}}-worker` |
| `companionWorker.entrypoint` | `exec am-support-agent-worker` |
| `TEMPORAL_TASK_QUEUE` | From Vault (`am-agents-ops`); must be `support-agent-v2` |

Shared application runtime env—including non-secret toggles—is injected from
Vault `apps/data/{env}/services/am-agents-ops` (see `vault-mappings.yaml`).
Profile identity (`DEPLOYMENT_ENVIRONMENT`, `SUPPORT_AGENT_RUNTIME_MODE`) stays
in `values.<env>.yaml`; Helm also keeps chart settings such as image and resources.

Canary / rollback env:

| Env | Meaning | Source |
|-----|---------|--------|
| `GROWTHBOOK_ENABLED` | Use GrowthBook as runtime routing source | Vault |
| `GROWTHBOOK_API_HOST` | Self-hosted GrowthBook API | Vault |
| `GROWTHBOOK_CLIENT_KEY` | SDK Connection key | Vault |
| `GROWTHBOOK_ROUTE_FEATURE_KEY` | Route flag (default `support-agent-route`) | Vault |
| `SUPPORT_AGENT_CANARY_MODE` | `off` \| `shadow` \| `canary` | Vault |
| `SUPPORT_AGENT_CANARY_PERCENT` | 0–100 sticky hash share | Vault |
| `SUPPORT_AGENT_CANARY_ALLOWLIST` | comma-separated tracking/demand ids | Vault (optional) |
| `SUPPORT_AGENT_FORCE_LEGACY` | instant rollback to legacy route | Vault (optional) |

Preprod/prod read GrowthBook + Temporal from
`apps/data/{env}/services/am-agents-ops`. GrowthBook values `new` and
`legacy` select the new or legacy path; unavailable GrowthBook fails closed to
legacy.

Render locally (requires checkout of am-pipelines chart):

```bash
helm template am-support-agent ../am-pipelines/helm/universal-chart \
  -f support-agent/helm/values.yaml
```
