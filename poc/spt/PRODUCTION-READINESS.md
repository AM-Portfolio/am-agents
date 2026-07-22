# SPT production readiness

This POC is useful for local/preprod load checks. Treat the items below as the gate before calling SPT “production.”

## Must keep today

- **replicas: 1** for the SPT pod. Stop-run, live progress, and the k6 PID registry are **in-process**. Scaling beyond one replica breaks stop/progress unless runs move to a shared worker.
- See `k8s/deployment.yaml` (`replicas: 1`) and `app/runners/process_registry.py`.

## Gaps before production

| Area | POC today | Need |
|------|-----------|------|
| Run / config store | JSON files under `data/` | Shared DB (or object store + index) if HA or multi-pod |
| Stop / kill | In-memory PID map | Job worker or sticky routing + shared cancel flag |
| Portal auth | Open UI | SSO / basic auth + audit who started/stopped |
| Target secrets | `.env` / k8s env | Secret manager; rotate identity password |
| Concurrent runs | Unlimited overlapping daemon threads | Queue + max concurrent runs + max VUs per tenant |
| Catalog | YAML baked into image | Versioned catalog + per-env base URLs |
| Observability | Influx run-summary (`spt_run` / `spt_api`) + Grafana UID `spt-load-testing` | Live k6 series, alerts, compare-runs; keep `INFLUXDB_TOKEN` secret |
| Safety | No hard tenant quotas | Caps on VUs, duration, APIs per run; dry-run mode |
| Multi-service scale | Manual API picker | Saved suites / tags; exclude flaky APIs by default |

## Already improved in this POC

- Pass/fail counts in history (not only FAILED)
- Live per-API progress
- **Stop** running k6 tests
- **Selective APIs** (run one of many)
- Portal split into `static/css` + `static/js` modules
- Influx run-summary metrics + Grafana board `spt-load-testing` (see [docs/METRICS.md](docs/METRICS.md))

## Suggested next production slice

1. Persist cancel + run status only (already file-backed) and add a small **run queue** with max concurrency = 1–2.
2. Portal auth (even HTTP basic behind Traefik) + `triggered_by` from identity.
3. Move secrets out of plain deployment YAML.
4. Only then consider replicas > 1 with an external runner.
