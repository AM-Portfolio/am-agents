# SPT Phase 0 POC Result — OSS Load Test Portal

Fill after smoke test.

- **Date:**
- **Operator:**
- **Cluster:** kind-am-preprod
- **Namespace:** load-testing
- **Portal URL:** https://am.asrax.in/spt-poc/ui
- **Grafana:** https://grafana.asrax.in/d/spt-load-testing/spt-load-testing (folder **AM / Platform**)
- **Runner:** k6-local (+ Testkube optional)
- **Influx bucket:** `load-testing-dev` (org `am-portfolio`)

## Result

- [ ] PASS
- [ ] PARTIAL
- [ ] FAIL

## Checks

| # | Check | Status | Notes |
|---|--------|--------|-------|
| 1 | Portal loads, filters work | | |
| 2 | k6 smoke run passes | | |
| 3 | Payloads editable + re-run | | |
| 4 | Metrics strip populated | | |
| 5 | Grafana `spt-load-testing` opens with run vars | | |
| 5b | Influx has `spt_run` / `spt_api` for run id | | |
| 6 | Config save/load | | |
| 7 | Service filter works | | |

## Evidence

- Run ID:
- RPS / p90 / error rate:
- Grafana screenshot:

## Sign-off

- **Ready for Phase 1?** YES / NO
