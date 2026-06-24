# AM Tool Agent

Greenfield replacement for db-agent with plugin-based integrations under `tools/`.

## Quick start (local)

```bash
cd am-agents/tool-agent
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8141
```

- Health: `http://localhost:8141/health`
- API: `POST /api/v1/tools/plan`, `/query`, `/execute`

## Add a tool

```bash
python scripts/new_tool.py mongodb --keywords mongo,mongodb --has-entities --enable
python scripts/validate_tool.py mongodb
```

See [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md) and [docs/PROMPT_MANAGEMENT.md](docs/PROMPT_MANAGEMENT.md).

## Postman

Import from [`postman/`](postman/):

1. **Collection:** `tool-agent-preprod.postman_collection.json`
2. **Environment:** `tool-agent-local.postman_environment.json` (port 8141) or `tool-agent-preprod.postman_environment.json` (`https://am.asrax.in/tools`)

Select an environment, then run **Health** → **Plan** → **Execute** (or **Query** for NL one-shot). Replace `portfolioId`, `userId`, and `sessionId` with real values before entity-centric requests.

Preprod HTTPS requires Traefik `strip-prefix-apps` to include `/tools` (see `am-infra/k8s/middleware-strip-prefix-apps-preprod.yaml`). If Cloudflare blocks requests (error 1010), test via port-forward or PowerShell `Invoke-RestMethod`.

Scripted smoke tests: `python scripts/test_ingress_preprod.py`.

## Deploy

Preprod ingress: `https://am.asrax.in/tools` (parallel to db-agent `/db`).
