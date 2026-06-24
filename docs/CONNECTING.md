# Connecting to db-agent

## HTTP API (ready now)

Start db-agent on `:8140`, then:

```bash
# Natural language query
curl -X POST http://localhost:8140/api/v1/db/query \
  -H "Content-Type: application/json" \
  -d '{"query":"list qdrant collections","read_only":true,"include_summary":false}'

# Plan only — see intent before execution
curl -X POST http://localhost:8140/api/v1/db/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"how many documents in portfolios","backend":"mongodb"}'

# Structured execute — no LLM re-parse
curl -X POST http://localhost:8140/api/v1/db/execute \
  -H "Content-Type: application/json" \
  -d '{"intent":{"backend":"qdrant","operation":"list_collections","params":{},"read_only":true,"confidence":1.0,"rationale":"manual"},"include_summary":false}'
```

## Cursor IDE

**Option A — Terminal / Composer:** paste curl or use db-agent while developing.

**Option B — Custom MCP (recommended next step):** add to Cursor `mcp.json` a stdio server that wraps db-agent HTTP (Phase 2 thin bridge). Until then, use HTTP from scripts.

**Option C — Agent header:** when calling from another agent:

```http
X-Agent-Caller: cursor
```

Requires `backend` in body and enforces confidence ≥ `DB_AGENT_INTENT_MIN_CONFIDENCE`.

## kagent

[kagent](https://github.com/kagent-dev/kagent) handles **Kubernetes** (pods, logs, deployments).  
db-agent handles **data stores** (Mongo, Redis, Kafka, Qdrant, Loki).

Phase 2: register db-agent as `RemoteMCPServer` in kagent so one ops agent can use both.

## Langfuse

- Enable `LANGFUSE_ENABLED=true` in `.env`
- Gateway mode (`LLM_ROUTING=gateway`): LLM traces in Langfuse via gateway
- Pipeline spans: db-agent trace id = `request_id` in response

Verify: `python scripts/e2e_qdrant_langfuse.py`
