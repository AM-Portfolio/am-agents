# CI

Canonical workflow: [`.github/workflows/support-agent.yml`](../../../.github/workflows/support-agent.yml)

Jobs:

1. **test** — `pip install -e ".[dev,temporal]"`, `pytest -q`, `compileall` (Python 3.11)
2. **helm** — lint/render `deploy/helm/` (PVC scaffold) + assert `helm/values.yaml` for universal-chart companion worker
3. **publish** — reusable `central-build-publish` (image `am-support-agent`, deploy_dev on)

Path filters: `support-agent/**` and the workflow file itself.

Central values live at `support-agent/helm/` (not `deploy/helm/`).
