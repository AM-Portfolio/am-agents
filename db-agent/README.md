# db-agent

Natural-language interface to AM infrastructure databases (Postgres, Mongo, Redis, Qdrant, Kafka, Grafana/Influx/Loki).

## Quick start

```bash
cd am-agents/db-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
npm run preprod
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/db/query` | NL question → intent → execute |
| POST | `/api/v1/db/plan` | Intent only (verify collection/operation before run) |
| POST | `/api/v1/db/execute` | Structured intent — skips LLM parse |
| GET | `/health` | Liveness |
| GET | `/ready` | Registry + LLM routing health |

### Example — collection count

```http
POST /api/v1/db/query
Content-Type: application/json

{
  "query": "how many documents in portfolio-db.portfolios",
  "backend": "mongodb",
  "read_only": true,
  "include_summary": false
}
```

### Example — plan then execute

```http
POST /api/v1/db/plan
{"query": "list qdrant collections", "backend": "qdrant"}

POST /api/v1/db/execute
{
  "intent": {
    "backend": "qdrant",
    "operation": "list_collections",
    "params": {},
    "read_only": true,
    "confidence": 1.0,
    "rationale": "confirmed"
  }
}
```

## LLM routing

| `LLM_ROUTING` | Path |
|---------------|------|
| `gateway` (preprod) | db-agent → am-mcp-gateway `/api/v1/agent/llm/completions` → LiteLLM → Langfuse |
| `direct` (local) | db-agent → LiteLLM directly |

Set in `.env`: `MCP_GATEWAY_BASE_URL`, `AM_MCP_CLIENT_SECRET`, `KEYCLOAK_TOKEN_URL` for gateway mode.

## Langfuse

- **Pipeline spans** (parse_intent, safety, execute, format): db-agent `DbAgentTracer` when `LANGFUSE_ENABLED=true`
- **LLM generations**: gateway mode logs via gateway/LiteLLM (no duplicate generation in db-agent)
- Verify: `python scripts/e2e_qdrant_langfuse.py`

## Connect from Cursor or other agents

### 1. HTTP (works today)

- **Cursor**: use a custom MCP server that proxies to db-agent HTTP, or call from terminal:
  ```bash
  curl -X POST http://localhost:8140/api/v1/db/query -H "Content-Type: application/json" -d "{\"query\":\"list qdrant collections\"}"
  ```
- **Any agent**: call `/plan` → review intent → `/execute` with structured JSON
- **Agent header**: `X-Agent-Caller: cursor` enforces `backend` hint + confidence threshold

### 2. kagent (Phase 2)

Register db-agent as `RemoteMCPServer` in [kagent](https://github.com/kagent-dev/kagent) — kagent handles K8s; db-agent handles data stores.

### 3. Cursor MCP config (optional)

Add an HTTP-based MCP or stdio wrapper that calls db-agent. Phase 2 can ship a thin `db-agent-mcp` stdio bridge.

## MCP deployment

| Env | Default | Description |
|-----|---------|-------------|
| `MCP_ENABLED` | `false` | Native adapters locally; MCP in preprod |
| `TOOLBOX_URL` | — | HTTP Toolbox sidecar for Postgres/Mongo/Redis |

Satellites: [`config/servers.yaml`](config/servers.yaml)  
Registry: [`config/registry.yaml`](config/registry.yaml)

## Design

See [`../docs/DB_AGENT_DESIGN.md`](../docs/DB_AGENT_DESIGN.md).
