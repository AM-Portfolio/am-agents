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

## Deploy

Preprod ingress: `https://am.asrax.in/tools` (parallel to db-agent `/db`).
