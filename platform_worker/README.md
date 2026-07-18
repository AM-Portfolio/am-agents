# Platform worker (Phase 1)

Temporal worker for AlertIncident MVP. Ports via `am_platform_ports`; adapters via `am_platform_adapters`.

## Run (local → cluster Temporal via port-forward)

```powershell
$env:KUBECONFIG="F:\am-repos\am-repos\VPS\VPS\kubeconfig.vps"
kubectl -n temporal port-forward svc/temporal-frontend 7233:7233

cd am-agents/platform_worker
pip install -e ../libs/platform-ports -e ../libs/agent-common -e ../libs/platform-adapters -e ".[dev]"

$env:TEMPORAL_HOST="localhost:7233"
$env:TEMPORAL_TASK_QUEUE="agent-platform"
$env:ALERT_NOTIFY_PROVIDER="cliq"
$env:TICKET_PROVIDER="fake"
$env:AM_PLATFORM_ENV_FILE="F:\am-repos\am-repos\am-obs-platform\.env"
python -m platform_worker.worker_main
```

Smoke (other terminal):

```powershell
$env:TEMPORAL_HOST="localhost:7233"
python -c "from platform_worker.__main_smoke__ import main; import asyncio; asyncio.run(main())"
```

Check **opslab** Cliq for the ticket.created card. UI: http://127.0.0.1:8080

In-cluster: `TEMPORAL_HOST=temporal-frontend.temporal.svc.cluster.local:7233`

```text
# One-time namespace:
kubectl exec -n temporal deploy/temporal-admintools -- temporal operator namespace create --namespace default --retention 7d
```
