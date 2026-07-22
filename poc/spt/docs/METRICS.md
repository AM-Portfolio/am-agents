# SPT metrics (Influx) — v1 run summary

Post-run points written by `am-spt-poc` when `INFLUXDB_TOKEN` is set.

| | |
|--|--|
| Org | `am-portfolio` |
| Bucket | `load-testing-dev` |
| Grafana board | UID `spt-load-testing` (am-obs-platform static) |
| Folder | **AM / Platform** |

## Measurements

### `spt_run`

Tags: `service`, `environment`, `run_id`, `profile`, `status`  
Fields: `rps`, `p50`, `p90`, `p95`, `p99`, `error_rate`, `vus`, `iterations`, `api_pass`, `api_fail`, `api_count`, `duration_s`

Written for **passed / failed / cancelled** finishes.

### `spt_api`

Tags: `service`, `environment`, `run_id`, `api_id`, `method`  
Fields: `requests`, `pass`, `fail`, `avg_ms`, `p90_ms`, `p95_ms`, `error_rate`, `http_status`

### Legacy (compat)

`k6_run` and `http_req_duration` still written for one release.

## Empty dashboard?

Usually missing `INFLUXDB_TOKEN` on the SPT pod (secret `am-spt-poc-influx` / key `token`).

```powershell
$env:KUBECONFIG = "F:\am-repos\am-repos\VPS\VPS\kubeconfig.vps"
kubectl -n load-testing create secret generic am-spt-poc-influx --from-literal=token='<INFLUX_TOKEN>' --dry-run=client -o yaml | kubectl apply -f -
kubectl -n load-testing rollout restart deployment/am-spt-poc
```

Also create bucket `load-testing-dev` in Influx if it does not exist.

## Portal deep link

`GRAFANA_K6_DASHBOARD_UID=spt-load-testing`  
URL pattern: `/d/spt-load-testing/spt-load-testing?var-service=…&var-environment=…&var-run_id=…`

## Not in v1

Live VU / per-request timeseries during the run (Phase 2: Prom remote-write or xk6-influx).
