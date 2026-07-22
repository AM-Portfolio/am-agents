# SPT Phase 0 POC — am-spt-poc

Minimal adapter to prove OctoPerf + MCP + k6 + Playwright before production SPT design.

## Quick start (local portal — preferred for UI work)

```powershell
cd F:\am-repos\am-repos\am-agents\poc\spt
.\scripts\run-local.ps1
```

1. Opens **http://localhost:8150/ui** (uvicorn `--reload` — edit HTML/Python and refresh)
2. Uses `.env` for identity login + analysis base URL (no Docker/VPS rebuild)
3. Use **APIs** to pick endpoints (default = all), **Run test**, **Stop** to cancel a live run
4. Click an API for Postman-style request/response (debug profile for full traces)

See [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md) before scaling beyond a single replica.

```powershell
copy .env.example .env   # set SPT_AUTH_PASSWORD
# K6_BIN=./vendor/bin/k6.exe on Windows (script downloads if missing)
```

### Manual local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8150
```

## Quick start (legacy smoke scripts)

```powershell
cd F:\am-repos\am-repos\am-agents\poc\spt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env — set OCTOPERF_MCP_URL and optional token/workspace/project IDs

# MCP ping
python scripts/ping.py

# Full smoke (7 steps)
python scripts/smoke_test.py

# HTTP API
uvicorn app.main:app --port 8150
curl http://localhost:8150/ping
curl -X POST http://localhost:8150/smoke
```

## Preprod Kubernetes deploy (only when sharing UI)

**Namespace:** `load-testing` (isolated from `am-apps-preprod` — shared app namespace).

Deploy only after local verify:

```powershell
.\scripts\vps-build-load.ps1
.\scripts\deploy-dev.ps1 -SkipBuild -SkipPush
```

Portal: https://am.asrax.in/spt-poc/ui  
Grafana: https://grafana.asrax.in/d/spt-load-testing/spt-load-testing (AM / Platform)  
Metrics: [docs/METRICS.md](docs/METRICS.md) — Influx `load-testing-dev`, requires `INFLUXDB_TOKEN` secret `am-spt-poc-influx`.

### 1. Install OctoPerf (optional — or use SaaS MCP)

```powershell
$env:KUBECONFIG = "F:\am-repos\am-repos\VPS\VPS\kubeconfig.vps"   # VPS/VPS/kubeconfig.vps
F:\am-repos\am-repos\am-infra\k8s\load-testing\octoperf\install.ps1
```

### 2. Vault secrets

Create `apps/data/preprod/services/am-spt-poc` in Vault:

| Key | Example |
|-----|---------|
| `OCTOPERF_MCP_URL` | `https://api.octoperf.com/mcp` or in-cluster URL |
| `OCTOPERF_MCP_TOKEN` | OAuth token if required |
| `OCTOPERF_WORKSPACE_ID` | from OctoPerf UI |
| `OCTOPERF_PROJECT_ID` | from OctoPerf UI |
| `POC_TARGET_URL` | `https://httpbin.org/get` |

### 3. Deploy spt-poc (recommended — native, no Docker/Vault)

```powershell
# Uses VPS/VPS/kubeconfig.vps → namespace load-testing
.\scripts\deploy-preprod-native.ps1
```

**Option B — helm + Docker image** (when image is built):

```powershell
# Uses VPS/VPS/kubeconfig.vps by default (kind-am-preprod @ 203.174.22.129)
.\scripts\deploy-preprod.ps1 -ImageTag local-poc -LocalPoc
```

**Option C — vault + secrets (production-like preprod):**

```powershell
.\scripts\deploy-preprod.ps1 -ImageTag <ghcr-tag> -SkipBuild
```

Apply ingress strip-prefix (once per cluster):

```powershell
$env:KUBECONFIG = "F:\am-repos\am-repos\VPS\VPS\kubeconfig.vps"
kubectl apply -f F:\am-repos\am-repos\am-infra\k8s\ingress-routing.yaml
```

### 4. Verify in preprod

```bash
curl https://am.asrax.in/spt-poc/health
curl https://am.asrax.in/spt-poc/ping
curl -X POST https://am.asrax.in/spt-poc/smoke
```

### 5. Document result

Update [POC-RESULT.md](./POC-RESULT.md). **Do not start Phase 1 until PASS.**

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness |
| `/ready` | GET | Readiness + MCP URL |
| `/ping` | GET | MCP connect + list tools |
| `/smoke` | POST | Full Phase 0 smoke test |
| `/config` | GET | Non-secret config preview |

## Files

```
poc/spt/
├── app/              # FastAPI + MCP client + OctoPerf ops
├── k6/               # smoke-get.js
├── playwright/       # smoke-navigate.spec.ts
├── helm/             # universal-chart values
├── scripts/          # ping, smoke_test, deploy-preprod
├── Dockerfile
└── POC-RESULT.md
```
