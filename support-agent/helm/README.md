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
| `TEMPORAL_TASK_QUEUE` | Must stay `support-agent-v2` (never `agent-platform`) |

Canary / rollback env:

| Env | Meaning |
|-----|---------|
| `GROWTHBOOK_ENABLED` | Use GrowthBook as runtime routing source |
| `GROWTHBOOK_API_HOST` | Self-hosted GrowthBook API |
| `GROWTHBOOK_CLIENT_KEY` | SDK Connection key, injected from Vault |
| `GROWTHBOOK_ROUTE_FEATURE_KEY` | Route flag (default `support-agent-route`) |
| `SUPPORT_AGENT_CANARY_MODE` | `off` \| `shadow` \| `canary` |
| `SUPPORT_AGENT_CANARY_PERCENT` | 0–100 sticky hash share |
| `SUPPORT_AGENT_CANARY_ALLOWLIST` | comma-separated tracking/demand ids |
| `SUPPORT_AGENT_FORCE_LEGACY` | instant rollback to legacy route |

Preprod reads `GROWTHBOOK_CLIENT_KEY` from
`apps/data/preprod/services/am-support-agent`. GrowthBook values `new` and
`legacy` select the new or legacy path; unavailable GrowthBook fails closed to
legacy.

Render locally (requires checkout of am-pipelines chart):

```bash
helm template am-support-agent ../am-pipelines/helm/universal-chart \
  -f support-agent/helm/values.yaml
```
