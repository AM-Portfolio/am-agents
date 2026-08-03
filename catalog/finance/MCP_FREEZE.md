# Freeze notice — am-mcp-server (Java)

Tool SoT is Java `am-mcp-server` (`list_tools`). Contract:
[`am-core-services/services/am-mcp-server/docs/MCP_CONTRACT.md`](../../../am-core-services/services/am-mcp-server/docs/MCP_CONTRACT.md)
(v1 envelope `{ok,data|error}`).

Fin-agent discovers and caches schemas at runtime; do not reintroduce a static
`tools.yaml` catalog for chat.

When adding a tool:
1. Implement in am-mcp-server with honest `@ToolParam(required=...)`
2. Add `artifactType` mapping in fin-agent `artifact_resolver.py` if the UI needs a typed artifact
3. Flutter maps that `artifactType` (see `ai_intent_response.dart`)

Do not add hand-written portfolio data tools back onto the fin-agent chat path.
Blocklist `ask_finance_agent` in fin-agent.
