# Support Agent Helm chart (local scaffold)

Parallel deploy only — does not replace legacy gateway/worker charts.

For **central** publish/deploy (universal-chart + companion worker), use
[`../helm/`](../helm/README.md) instead.

```bash
helm lint support-agent/deploy/helm
helm template support-agent support-agent/deploy/helm
helm template support-agent support-agent/deploy/helm \
  --set worker.enabled=true \
  --set persistence.enabled=true \
  --set persistence.storageClassName=standard
```

Identities (standalone chart):

| Resource | Name |
|----------|------|
| Gateway Deployment/Service | `support-agent-gateway` |
| Worker Deployment (optional) | `support-agent-worker` |
| Temporal queue | `support-agent-v2` (never `agent-platform`) |
| SQLite PVC (optional) | `support-agent-gateway-data` |
