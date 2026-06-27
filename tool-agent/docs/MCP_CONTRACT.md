# AM Tool Agent MCP Contract v1.0.0

Portable integration surface for kagent, cloud agents, and IDEs.

## Transports

| Transport | Entry | Use case |
|-----------|-------|----------|
| MCP stdio | `scripts/mcp_stdio_bridge.py` | Cursor, VS Code, Windsurf, Claude Desktop |
| MCP HTTP | `scripts/mcp_http_server.py` `/mcp` | kagent `RemoteMCPServer`, in-cluster agents |
| REST | `POST /api/v1/tools/{plan,query,execute}` | HTTP agents, OpenAPI clients |
| SSE | `POST /api/v1/tools/{plan,query,execute}/stream` | Live stage streaming |

Set `TOOL_AGENT_CALLER` (stdio/HTTP MCP) or `X-Agent-Caller` (REST) for audit and agent policy.

## MCP tools

| Tool | REST | Description |
|------|------|-------------|
| `tool_agent_health` | GET `/health` | Liveness |
| `tool_agent_ready` | GET `/ready` | Readiness + catalog cache |
| `tool_agent_list_backends` | GET `/health` | Enabled backend names |
| `tool_agent_plan` | POST `/plan` or `/plan/stream` | Intent + resolve, no execute |
| `tool_agent_execute` | POST `/execute` or `/execute/stream` | Structured intent → data |
| `tool_agent_query` | POST `/query` or `/query/stream` | One-shot (IDE only; kagent uses plan+execute) |

When `TOOL_AGENT_MCP_USE_STREAM=true` (default), MCP tools call `/stream` endpoints and return a `stages` array in the JSON envelope.

## SSE event types

`stage`, `intent`, `resolved`, `safety`, `result`, `token`, `done`, `error`

## Cloud integration (later)

- **AWS Bedrock / Azure / Vertex:** point action group or connected tool at MCP HTTP URL or REST OpenAPI
- **LiteLLM MCP hub:** register `http://am-tool-agent-mcp.kagent:8085/mcp`

## Versioning

Bump `MCP_CONTRACT_VERSION` in `scripts/mcp_tools.py` when tool schemas change.
