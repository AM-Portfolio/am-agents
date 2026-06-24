# Connecting to tool-agent

## Recommended: Cursor MCP (stdio bridge → live HTTP)

tool-agent exposes a **REST API**, not a native MCP server. The recommended Cursor setup is a **local stdio MCP bridge** that proxies to the live API.

```mermaid
flowchart LR
  Cursor[Cursor mcp.json]
  Bridge[mcp_stdio_bridge.py]
  API[https://am.asrax.in/tools]

  Cursor -->|stdio| Bridge
  Bridge -->|httpx| API
```

**Why this approach**

- Works with live preprod today (`https://am.asrax.in/tools`)
- No change to cluster ingress or am-mcp-gateway required
- Separate from in-cluster `MCP_ENABLED` / toolbox (adapters run directly in preprod)

### Setup

1. Install deps (includes `mcp` SDK):

```bash
cd am-agents/tool-agent
pip install -r requirements.txt
```

2. Copy [`mcp.json.example`](../mcp.json.example) into Cursor MCP settings. Update the `args` path to your machine:

```json
{
  "mcpServers": {
    "am-tool-agent-preprod": {
      "command": "python",
      "args": ["a:/InfraCode/AM-Portfolio-grp/am-agents/tool-agent/scripts/mcp_stdio_bridge.py"],
      "env": {
        "TOOL_AGENT_BASE_URL": "https://am.asrax.in/tools",
        "TOOL_AGENT_CALLER": "cursor-mcp"
      }
    }
  }
}
```

3. Restart Cursor MCP. You should see tools:

| MCP tool | Purpose |
|----------|---------|
| `tool_agent_health` | GET `/health` |
| `tool_agent_ready` | GET `/ready` |
| `tool_agent_plan` | POST `/api/v1/tools/plan` |
| `tool_agent_query` | POST `/api/v1/tools/query` |
| `tool_agent_execute` | POST `/api/v1/tools/execute` (pass `intent_json`) |

4. Smoke test without Cursor:

```bash
python scripts/test_mcp_bridge.py
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TOOL_AGENT_BASE_URL` | `https://am.asrax.in/tools` | API base (no trailing slash required) |
| `TOOL_AGENT_CALLER` | (empty) | Sets `X-Agent-Caller` header when set |

## HTTP API (Postman / curl)

See [`postman/`](../postman/) or:

```bash
curl -sS https://am.asrax.in/tools/health
curl -sS -X POST https://am.asrax.in/tools/api/v1/tools/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"list mongo databases","backend":"mongodb","read_only":true}'
```

## Not the same as internal toolbox MCP

- **`mcp/pool.py`** in tool-agent is for calling Mongo/Redis toolbox MCP servers when `MCP_ENABLED=true`
- Preprod runs **`MCP_ENABLED=false`** and uses Python **adapters** directly
- Cursor `mcp.json` talks to the **tool-agent HTTP API**, not raw Mongo MCP

## Preprod caveats

- Traefik `strip-prefix-apps` must include `/tools`
- If Python gets Cloudflare 1010, use PowerShell `Invoke-RestMethod` or the stdio bridge (often works)
